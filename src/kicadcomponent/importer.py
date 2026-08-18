"""Envoltorio sobre easyeda2kicad.

easyeda2kicad se instala como dependencia, asi que se llama importando su
`main()` en vez de lanzar un proceso: no hay venv que activar ni ejecutable que
buscar en el PATH, y funciona igual en Linux, macOS y Windows.
"""

from __future__ import annotations

from typing import List

from .project import LibraryPaths

#: Que descargar. La clave es lo que el usuario escribe; el valor, la opcion real.
MODES = {
    "full": "--full",
    "symbol": "--symbol",
    "footprint": "--footprint",
    "3d": "--3d",
}


class ImportError_(RuntimeError):
    """La descarga fallo."""


def build_args(lcsc_id: str, paths: LibraryPaths, mode: str, overwrite: bool) -> List[str]:
    if mode not in MODES:
        raise ValueError(f"modo desconocido: {mode}")
    args = [MODES[mode], f"--lcsc_id={lcsc_id}", f"--output={paths.output_base}"]
    if overwrite:
        args.append("--overwrite")
    return args


def import_component(
    lcsc_id: str, paths: LibraryPaths, mode: str = "full", overwrite: bool = True
) -> int:
    """Descarga el componente. Devuelve el codigo de salida de easyeda2kicad."""
    try:
        from easyeda2kicad.__main__ import main as easyeda_main
    except ImportError as exc:  # pragma: no cover - solo si falta la dependencia
        raise ImportError_(
            "no se pudo importar easyeda2kicad; reinstala kicadcomponent"
        ) from exc

    paths.root.mkdir(parents=True, exist_ok=True)
    args = build_args(lcsc_id, paths, mode, overwrite)

    # main() usa argparse por dentro, asi que ante un argumento invalido lanza
    # SystemExit en lugar de devolver un codigo.
    try:
        return easyeda_main(args) or 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
