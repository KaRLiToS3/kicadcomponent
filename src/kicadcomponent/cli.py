"""Interfaz de linea de comandos."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .importer import MODES, import_component
from .library import AmbiguousQuery, ComponentNotFound, Library, LibraryError, RemovalPlan
from .project import DEFAULT_NICKNAME, LibraryPaths, ProjectError, find_project, resolve_library

SUBCOMMANDS = ("add", "remove", "list", "where")


# ------------------------------------------------------------------- colores

class Style:
    """ANSI, pero solo cuando la salida es una terminal que lo entiende."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def red(self, text: str) -> str:
        return self(text, "31")

    def green(self, text: str) -> str:
        return self(text, "32")

    def yellow(self, text: str) -> str:
        return self(text, "33")

    def cyan(self, text: str) -> str:
        return self(text, "36")

    def dim(self, text: str) -> str:
        return self(text, "2")


def _make_style() -> Style:
    if os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty():
        return Style(False)
    if sys.platform == "win32":  # pragma: no cover - solo Windows
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING sobre STD_OUTPUT_HANDLE
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            return Style(False)
    return Style(True)


style = _make_style()


def fail(message: str) -> int:
    print(style.red(f"Error: {message}"), file=sys.stderr)
    return 1


# -------------------------------------------------------------------- ordenes

def _library(args: argparse.Namespace) -> LibraryPaths:
    project = Path(args.project).expanduser() if args.project else None
    return resolve_library(
        project_dir=project,
        nickname=args.nickname,
        lib_root=Path(args.lib).expanduser() if args.lib else None,
    )


def cmd_where(args: argparse.Namespace) -> int:
    paths = _library(args)
    if paths.project_dir:
        print(f"  proyecto   {paths.project_dir}")
    print(paths.describe())
    missing = [
        label
        for label, path in (
            ("simbolos", paths.sym_path),
            ("footprints", paths.pretty_dir),
            ("modelos 3D", paths.shapes_dir),
        )
        if not path.exists()
    ]
    if missing:
        print(style.dim(f"  (aun no existen: {', '.join(missing)})"))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    library = Library(_library(args))
    components = library.components
    if not components:
        print(f"La libreria no tiene simbolos todavia: {library.paths.sym_path}")
        return 0

    rows = [
        (
            component.lcsc or "-",
            component.name,
            component.footprint or "-",
            library.model_for(component.footprint) or "-" if component.footprint else "-",
        )
        for component in sorted(components, key=lambda c: c.name.lower())
    ]
    header = ("LCSC", "SIMBOLO", "FOOTPRINT", "MODELO 3D")
    widths = [max(len(row[i]) for row in (*rows, header)) for i in range(4)]
    line = "  ".join
    print(style.cyan(line(value.ljust(width) for value, width in zip(header, widths))))
    print(style.dim(line("-" * width for width in widths)))
    for row in rows:
        print(line(value.ljust(width) for value, width in zip(row, widths)))
    plural = "componente" if len(rows) == 1 else "componentes"
    print(f"\n{len(rows)} {plural} en {library.paths.root}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    paths = _library(args)
    failed = 0
    for lcsc_id in args.lcsc_id:
        # easyeda2kicad escribe por stderr sin buffer: sin flush saldria despues
        print(style.cyan(f"Importando {lcsc_id} ({args.mode}) en {paths.root}"), flush=True)
        code = import_component(lcsc_id, paths, mode=args.mode, overwrite=not args.no_overwrite)
        if code:
            print(style.red(f"  {lcsc_id}: easyeda2kicad devolvio {code}"), file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def _print_plan(plan: RemovalPlan, library: Library) -> None:
    print(style.yellow(f"Se va a borrar de {library.paths.root}:"))
    if plan.symbol:
        suffix = f"  ({plan.lcsc})" if plan.lcsc else ""
        print(f"  simbolo    {plan.symbol}{suffix}")
    else:
        print("  simbolo    (ninguno, solo hay footprint)")
    files = [str(path) for path in plan.delete]
    if files:
        for path in files:
            print(f"  fichero    {path}")
    else:
        print("  fichero    (ninguno)")
    for note in plan.notes:
        print(style.cyan(f"  nota: {note}"))


def cmd_remove(args: argparse.Namespace) -> int:
    library = Library(_library(args))

    try:
        plan = library.plan_removal(args.query)
    except ComponentNotFound:
        print(
            style.red(f"No hay ningun componente que encaje con '{args.query}' en:"),
            file=sys.stderr,
        )
        print(f"  {library.paths.root}", file=sys.stderr)
        print("Prueba 'kicadcomponent list' para ver los nombres.", file=sys.stderr)
        return 1
    except AmbiguousQuery as exc:
        print(style.yellow(f"'{args.query}' encaja con varios componentes:"), file=sys.stderr)
        for candidate in exc.candidates:
            print(
                f"  {candidate.lcsc or '-'} | {candidate.name or '(sin simbolo)'} "
                f"| {candidate.footprint or '-'}",
                file=sys.stderr,
            )
        print("Concreta con el LCSC ID o el nombre exacto del simbolo.", file=sys.stderr)
        return 1

    if plan.is_empty:
        print("No hay nada que borrar.")
        for note in plan.notes:
            print(style.cyan(f"  nota: {note}"))
        return 0

    _print_plan(plan, library)

    if args.dry_run:
        print(style.dim("(--dry-run: no se ha tocado nada)"))
        return 0

    if not args.yes:
        try:
            reply = input("Confirmas el borrado? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            reply = ""
        if reply not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado, no se ha tocado nada.")
            return 1

    backup = library.apply(plan)
    if plan.symbol:
        print(style.green("  simbolo borrado") + style.dim(f" (copia en {backup})"))
    for path in plan.delete:
        print(style.green("  borrado ") + str(path))
    print(style.yellow("Refresca las librerias en KiCad para que deje de verlo."))
    return 0


# --------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kicadcomponent",
        description=(
            "Importa y elimina componentes de LCSC/EasyEDA en un proyecto KiCad, "
            "manteniendo simbolo, footprint y modelo 3D en sintonia."
        ),
        epilog=(
            "El proyecto se detecta solo subiendo desde el directorio actual hasta "
            "el .kicad_pro, y la libreria se lee de sym-lib-table / fp-lib-table."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", metavar="DIR", help="carpeta que contiene el .kicad_pro")
    common.add_argument("--lib", metavar="DIR", help="carpeta de la libreria, saltandose las lib-tables")
    common.add_argument(
        "--nickname", default=DEFAULT_NICKNAME, help=f"nombre de la libreria (por defecto: {DEFAULT_NICKNAME})"
    )

    subparsers = parser.add_subparsers(dest="command")

    add = subparsers.add_parser("add", parents=[common], help="descargar un componente de LCSC")
    add.add_argument("lcsc_id", nargs="+", help="uno o varios LCSC ID (C12345)")
    add.add_argument(
        "--mode", choices=sorted(MODES), default="full", help="que descargar (por defecto: full)"
    )
    add.add_argument("--symbol", dest="mode", action="store_const", const="symbol", help="solo el simbolo")
    add.add_argument("--footprint", dest="mode", action="store_const", const="footprint", help="solo el footprint")
    add.add_argument("--3d", dest="mode", action="store_const", const="3d", help="solo el modelo 3D")
    add.add_argument("--no-overwrite", action="store_true", help="no sobrescribir si ya existe")
    add.set_defaults(func=cmd_add)

    remove = subparsers.add_parser(
        "remove", parents=[common], aliases=["rm"], help="borrar simbolo, footprint y modelo 3D"
    )
    remove.add_argument("query", help="LCSC ID o nombre del simbolo")
    remove.add_argument("-y", "--yes", action="store_true", help="no preguntar")
    remove.add_argument("-n", "--dry-run", action="store_true", help="enseñar el plan y salir")
    remove.set_defaults(func=cmd_remove)

    listing = subparsers.add_parser("list", parents=[common], aliases=["ls"], help="inventario de la libreria")
    listing.set_defaults(func=cmd_list)

    where = subparsers.add_parser("where", parents=[common], help="rutas que se estan usando")
    where.set_defaults(func=cmd_where)

    return parser


def _with_default_command(argv: Sequence[str]) -> List[str]:
    """`kicadcomponent C12345` equivale a `kicadcomponent add C12345`."""
    args = list(argv)
    for index, value in enumerate(args):
        if value in ("-h", "--help", "--version"):
            return args
        if value in SUBCOMMANDS or value in ("rm", "ls"):
            return args
        if not value.startswith("-"):
            return args[:index] + ["add"] + args[index:]
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(_with_default_command(argv))
    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except (ProjectError, LibraryError) as exc:
        return fail(str(exc))
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrumpido.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
