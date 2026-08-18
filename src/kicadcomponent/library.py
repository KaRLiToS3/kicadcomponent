"""Inventario y borrado de componentes dentro de una libreria easyeda2kicad.

No hace falta ninguna base de datos aparte: la cadena completa ya esta escrita
en los propios ficheros de la libreria, asi que un indice paralelo solo podria
desincronizarse.

    LCSC Part -> simbolo    easyeda2kicad.kicad_sym  (property "LCSC Part" "C12345")
    simbolo   -> footprint  el mismo bloque          (property "Footprint" "lib:FP")
    footprint -> modelo 3D  FP.kicad_mod             (model ".../MODELO.wrl")
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .project import LibraryPaths
from .sexpr import Node, ParseError, parse

#: Extensiones que easyeda2kicad deja en la carpeta .3dshapes.
MODEL_EXTENSIONS = (".wrl", ".step", ".stp")


class LibraryError(RuntimeError):
    """Problema al leer o modificar la libreria."""


class ComponentNotFound(LibraryError):
    def __init__(self, query: str) -> None:
        super().__init__(f"ningun componente encaja con '{query}'")
        self.query = query


class AmbiguousQuery(LibraryError):
    def __init__(self, query: str, candidates: List["Component"]) -> None:
        super().__init__(f"'{query}' encaja con {len(candidates)} componentes")
        self.query = query
        self.candidates = candidates


class Component:
    """Un simbolo del .kicad_sym, con lo que cuelga de el."""

    __slots__ = ("name", "lcsc", "footprint", "footprint_lib", "start", "end")

    def __init__(
        self,
        name: str,
        lcsc: str,
        footprint: str,
        footprint_lib: Optional[str],
        start: int,
        end: int,
    ) -> None:
        self.name = name
        self.lcsc = lcsc
        self.footprint = footprint
        self.footprint_lib = footprint_lib
        self.start = start
        self.end = end

    def __repr__(self) -> str:  # pragma: no cover - solo para depurar
        return f"Component({self.name!r}, lcsc={self.lcsc!r})"


class RemovalPlan:
    """Que se borraria y que se conserva, antes de tocar nada."""

    __slots__ = ("symbol", "lcsc", "footprint", "model", "delete", "notes")

    def __init__(self) -> None:
        self.symbol: str = ""
        self.lcsc: str = ""
        self.footprint: str = ""
        self.model: str = ""
        self.delete: List[Path] = []
        self.notes: List[str] = []

    @property
    def is_empty(self) -> bool:
        return not self.symbol and not self.delete


def _model_name(reference: str) -> str:
    """Nombre del modelo a partir de la ruta guardada en el .kicad_mod."""
    base = reference.replace("\\", "/").rsplit("/", 1)[-1]
    stem, dot, ext = base.rpartition(".")
    if dot and f".{ext.lower()}" in MODEL_EXTENSIONS:
        return stem
    return base


def _properties(symbol: Node) -> Dict[str, str]:
    """Propiedades del simbolo, valga el estilo de easyeda2kicad o el de KiCad."""
    props: Dict[str, str] = {}
    for prop in symbol.find("property"):
        values = prop.values()[1:]  # el primero es "property"
        if len(values) >= 2:
            props[values[0]] = values[1]
    return props


class Library:
    def __init__(self, paths: LibraryPaths) -> None:
        self.paths = paths
        self._text: Optional[str] = None
        self._components: Optional[List[Component]] = None

    # ------------------------------------------------------------- lectura

    def _load(self) -> None:
        if self._components is not None:
            return
        if not self.paths.sym_path.is_file():
            self._text, self._components = "", []
            return
        self._text = self.paths.sym_path.read_text(encoding="utf-8")
        try:
            root = parse(self._text)
        except ParseError as exc:
            raise LibraryError(f"{self.paths.sym_path} no se puede leer: {exc}") from exc

        components: List[Component] = []
        for symbol in root.find("symbol"):
            names = symbol.values()[1:]
            if not names:
                continue
            props = _properties(symbol)
            raw_fp = props.get("Footprint", "")
            lib, _, bare = raw_fp.rpartition(":")
            components.append(
                Component(
                    name=names[0],
                    lcsc=props.get("LCSC Part", ""),
                    footprint=bare,
                    footprint_lib=lib or None,
                    start=symbol.start,
                    end=symbol.end,
                )
            )
        self._components = components

    @property
    def components(self) -> List[Component]:
        self._load()
        assert self._components is not None
        return self._components

    def footprint_file(self, footprint: str) -> Path:
        return self.paths.pretty_dir / f"{footprint}.kicad_mod"

    def footprint_names(self) -> List[str]:
        if not self.paths.pretty_dir.is_dir():
            return []
        return sorted(p.stem for p in self.paths.pretty_dir.glob("*.kicad_mod"))

    def model_for(self, footprint: str) -> Optional[str]:
        """Nombre del modelo 3D que usa un footprint.

        Solo sirve el nombre del fichero: la ruta guardada dentro del
        `.kicad_mod` puede venir de otra maquina (`/home/otro/...`).
        """
        path = self.footprint_file(footprint)
        if not path.is_file():
            return None
        try:
            root = parse(path.read_text(encoding="utf-8", errors="replace"))
        except (ParseError, OSError):
            return None
        for model in root.find_deep("model"):
            values = model.values()[1:]
            if values:
                return _model_name(values[0])
        return None

    def model_files(self, model: str) -> List[Path]:
        return [
            self.paths.shapes_dir / f"{model}{ext}"
            for ext in MODEL_EXTENSIONS
            if (self.paths.shapes_dir / f"{model}{ext}").is_file()
        ]

    def footprints_using_model(self, model: str, skip: str) -> List[str]:
        return [
            name
            for name in self.footprint_names()
            if name != skip and self.model_for(name) == model
        ]

    # ------------------------------------------------------------- busqueda

    def find(self, query: str) -> Optional[Component]:
        """Busca por LCSC ID o por nombre de simbolo, de exacto a parcial."""
        needle = query.strip().lower()
        for match in (
            [c for c in self.components if c.lcsc.lower() == needle],
            [c for c in self.components if c.name.lower() == needle],
            [c for c in self.components if needle in c.name.lower() or needle in c.lcsc.lower()],
        ):
            if len(match) == 1:
                return match[0]
            if match:
                raise AmbiguousQuery(query, match)
        return None

    # -------------------------------------------------------------- borrado

    def plan_removal(self, query: str) -> RemovalPlan:
        """Resuelve la cadena entera y decide que se puede borrar.

        Nunca se borra algo que siga en uso: un footprint compartido por otro
        simbolo se queda, y con el su modelo 3D.
        """
        plan = RemovalPlan()
        component = self.find(query)

        if component is not None:
            plan.symbol = component.name
            plan.lcsc = component.lcsc
            plan.footprint = component.footprint
            foreign = component.footprint_lib not in (None, "", self.paths.nickname)
        else:
            # Puede haberse importado solo el footprint (--footprint / --3d).
            needle = query.strip().lower()
            names = self.footprint_names()
            matches = [n for n in names if n.lower() == needle] or [
                n for n in names if needle in n.lower()
            ]
            if not matches:
                raise ComponentNotFound(query)
            if len(matches) > 1:
                raise AmbiguousQuery(
                    query, [Component("", "", n, None, 0, 0) for n in matches]
                )
            plan.footprint = matches[0]
            foreign = False

        drop_footprint = False
        if foreign:
            plan.notes.append(
                f"el footprint vive en la libreria '{component.footprint_lib}', no se toca"
            )
        elif plan.footprint:
            shared = [
                c.name
                for c in self.components
                if c.name != plan.symbol and c.footprint == plan.footprint
            ]
            fp_file = self.footprint_file(plan.footprint)
            if shared:
                plan.notes.append(
                    "el footprint se conserva, lo usan tambien: " + ", ".join(shared)
                )
            elif fp_file.is_file():
                plan.delete.append(fp_file)
                drop_footprint = True
            else:
                plan.notes.append(f"el fichero del footprint ya no existe: {fp_file}")

        if plan.footprint:
            model = self.model_for(plan.footprint)
            if model:
                plan.model = model
                if not drop_footprint:
                    plan.notes.append(
                        f"el modelo 3D se conserva, lo sigue usando {plan.footprint}"
                    )
                else:
                    shared_by = self.footprints_using_model(model, plan.footprint)
                    if shared_by:
                        plan.notes.append(
                            "el modelo 3D se conserva, lo usan tambien: "
                            + ", ".join(shared_by)
                        )
                    else:
                        files = self.model_files(model)
                        if files:
                            plan.delete.extend(files)
                        else:
                            plan.notes.append(f"no hay ficheros 3D para {model}")

        return plan

    def apply(self, plan: RemovalPlan) -> Optional[Path]:
        """Ejecuta el plan. Devuelve la ruta de la copia de seguridad, si la hubo."""
        backup: Optional[Path] = None
        if plan.symbol:
            backup = self._remove_symbol(plan.symbol)
        for path in plan.delete:
            path.unlink()
        self._components = None  # obliga a releer
        self._text = None
        return backup

    def _remove_symbol(self, name: str) -> Path:
        self._load()
        component = next((c for c in self.components if c.name == name), None)
        if component is None:
            raise LibraryError(f"no existe el simbolo '{name}'")

        path = self.paths.sym_path
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)

        text = self._text or ""
        start, end = component.start, component.end
        # Arrastra la sangria y el salto de linea para no dejar huecos.
        while start > 0 and text[start - 1] in " \t":
            start -= 1
        while end < len(text) and text[end] in " \t":
            end += 1
        if end < len(text) and text[end] == "\n":
            end += 1

        path.write_text(text[:start] + text[end:], encoding="utf-8")
        return backup
