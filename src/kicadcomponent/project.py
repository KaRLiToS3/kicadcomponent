"""Localizar el proyecto KiCad y, dentro de el, la libreria de easyeda2kicad.

No se adivinan rutas: KiCad ya guarda donde vive cada libreria en `sym-lib-table`
y `fp-lib-table`, junto al `.kicad_pro`. Leerlas es lo unico fiable, porque la
libreria no tiene por que estar dentro de la carpeta del proyecto:

    proyecto/
    ├── lib/easyeda2kicad/     <- la libreria, compartida
    ├── v1/esp32.kicad_pro     <- ${KIPRJMOD}/../lib/easyeda2kicad/...
    └── v2/esp32.kicad_pro
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

from .sexpr import ParseError, parse

DEFAULT_NICKNAME = "easyeda2kicad"
_MAX_SEARCH_DEPTH = 3


class ProjectError(RuntimeError):
    """No se pudo determinar el proyecto o la libreria."""


class LibraryPaths:
    """Las tres rutas que componen una libreria de easyeda2kicad."""

    __slots__ = ("nickname", "sym_path", "pretty_dir", "shapes_dir", "project_dir")

    def __init__(
        self,
        nickname: str,
        sym_path: Path,
        pretty_dir: Path,
        shapes_dir: Path,
        project_dir: Optional[Path] = None,
    ) -> None:
        self.nickname = nickname
        self.sym_path = sym_path
        self.pretty_dir = pretty_dir
        self.shapes_dir = shapes_dir
        self.project_dir = project_dir

    @property
    def output_base(self) -> Path:
        """Lo que espera `easyeda2kicad --output`: la ruta sin extension."""
        return self.sym_path.with_suffix("")

    @property
    def root(self) -> Path:
        return self.sym_path.parent

    def describe(self) -> str:
        return (
            f"  nickname   {self.nickname}\n"
            f"  simbolos   {self.sym_path}\n"
            f"  footprints {self.pretty_dir}\n"
            f"  modelos 3D {self.shapes_dir}"
        )


def find_project(start: Optional[Path] = None) -> Path:
    """Carpeta que contiene el `.kicad_pro`, subiendo desde `start`.

    Si no aparece por encima se busca por debajo, porque es habitual estar en la
    raiz del repositorio con los proyectos en subcarpetas (`v1/`, `v2/`...).
    """
    start = (start or Path.cwd()).resolve()

    for directory in (start, *start.parents):
        if any(directory.glob("*.kicad_pro")):
            return directory

    found: List[Path] = []
    for depth in range(1, _MAX_SEARCH_DEPTH + 1):
        pattern = "/".join(["*"] * depth) + "/*.kicad_pro"
        found.extend(sorted(start.glob(pattern)))
        if found:
            break

    if len(found) == 1:
        return found[0].parent
    if found:
        options = "\n".join(f"  {p.parent}" for p in found)
        raise ProjectError(
            f"Hay varios proyectos KiCad bajo {start}:\n{options}\n"
            "Entra en uno de ellos o indica cual con --project."
        )
    raise ProjectError(
        f"No se encontro ningun *.kicad_pro desde {start}.\n"
        "Entra en la carpeta del proyecto o usa --project / --lib."
    )


def _expand(uri: str, project_dir: Path) -> Path:
    """Resuelve `${KIPRJMOD}` y cualquier otra variable de entorno de KiCad."""
    uri = uri.replace("${KIPRJMOD}", str(project_dir)).replace("$(KIPRJMOD)", str(project_dir))
    uri = os.path.expandvars(uri)
    path = Path(uri).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return Path(os.path.normpath(str(path)))


def _read_lib_table(path: Path, nickname: str, project_dir: Path) -> Optional[Path]:
    """URI de la libreria `nickname` dentro de un fp-lib-table/sym-lib-table."""
    if not path.is_file():
        return None
    try:
        root = parse(path.read_text(encoding="utf-8"))
    except (ParseError, OSError):
        return None

    for lib in root.find("lib"):
        name = uri = None
        for field in lib.lists():
            values = field.values()
            if len(values) >= 2 and field.head == "name":
                name = values[1]
            elif len(values) >= 2 and field.head == "uri":
                uri = values[1]
        if name == nickname and uri:
            return _expand(uri, project_dir)
    return None


def resolve_library(
    project_dir: Optional[Path] = None,
    nickname: str = DEFAULT_NICKNAME,
    lib_root: Optional[Path] = None,
) -> LibraryPaths:
    """Rutas de la libreria, por las lib-tables o por convencion."""
    if lib_root is not None:
        # --lib apunta a la carpeta que contiene <nickname>.kicad_sym
        lib_root = Path(lib_root).expanduser().resolve()
        return LibraryPaths(
            nickname=nickname,
            sym_path=lib_root / f"{nickname}.kicad_sym",
            pretty_dir=lib_root / f"{nickname}.pretty",
            shapes_dir=lib_root / f"{nickname}.3dshapes",
            project_dir=project_dir,
        )

    project_dir = (project_dir or find_project()).resolve()

    sym_path = _read_lib_table(project_dir / "sym-lib-table", nickname, project_dir)
    pretty_dir = _read_lib_table(project_dir / "fp-lib-table", nickname, project_dir)

    if sym_path is None and pretty_dir is None:
        raise ProjectError(
            f"El proyecto {project_dir} no declara ninguna libreria llamada "
            f"'{nickname}'.\nImporta un componente primero, o indica la carpeta "
            "con --lib (o el nombre con --nickname)."
        )

    # Si sólo una de las dos tablas la declara, la otra se deduce a su lado.
    if sym_path is None:
        sym_path = pretty_dir.parent / f"{nickname}.kicad_sym"  # type: ignore[union-attr]
    if pretty_dir is None:
        pretty_dir = sym_path.parent / f"{nickname}.pretty"

    # easyeda2kicad siempre deja los modelos en <base>.3dshapes junto al .pretty
    shapes_dir = pretty_dir.parent / f"{pretty_dir.stem}.3dshapes"

    return LibraryPaths(
        nickname=nickname,
        sym_path=sym_path,
        pretty_dir=pretty_dir,
        shapes_dir=shapes_dir,
        project_dir=project_dir,
    )
