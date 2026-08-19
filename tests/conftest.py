"""Fixtures comunes.

Los ficheros de tests/data no son inventados: salen de un proyecto KiCad real
(un LM324N importado con easyeda2kicad), asi que traen consigo las rarezas que
el codigo tiene que aguantar y que un fixture escrito a mano no tendria:

  - propiedades multilinea, el estilo de easyeda2kicad
  - propiedades en una sola linea, el estilo del editor de KiCad (LM358P)
  - texto no ASCII dentro de una propiedad: "TI(德州仪器)"
  - un modelo 3D cuyo nombre NO es el del footprint (lleva un H5.1 de mas)
  - una ruta de modelo apuntando a otra maquina (/home/otro/...)
  - lib-tables con ${KIPRJMOD}/../lib/..., es decir la libreria fuera del proyecto
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"

#: Lo que contiene la libreria de ejemplo.
SYMBOL = "LM324N_NOPB"
LCSC = "C352847"
FOOTPRINT = "PDIP-14_L19.7-W6.6-P2.54-LS8.3-BL"
MODEL = "PDIP-14_L19.7-W6.6-H5.1-P2.54-LS8.3-BL"


class Project:
    """Un proyecto KiCad de mentira sobre disco, con el reparto de verdad:

        raiz/
        |-- lib/easyeda2kicad/easyeda2kicad.kicad_sym
        |                    /easyeda2kicad.pretty/<footprint>.kicad_mod
        |                    /easyeda2kicad.3dshapes/<modelo>.wrl + .step
        `-- CircuitoV5/CircuitoV5.kicad_pro
                      /sym-lib-table
                      /fp-lib-table
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.project_dir = root / "CircuitoV5"
        self.lib_dir = root / "lib" / "easyeda2kicad"
        self.sym_path = self.lib_dir / "easyeda2kicad.kicad_sym"
        self.pretty_dir = self.lib_dir / "easyeda2kicad.pretty"
        self.shapes_dir = self.lib_dir / "easyeda2kicad.3dshapes"

    @property
    def footprint_file(self) -> Path:
        return self.pretty_dir / f"{FOOTPRINT}.kicad_mod"

    def model_file(self, ext: str) -> Path:
        return self.shapes_dir / f"{MODEL}{ext}"


def _build(root: Path) -> Project:
    project = Project(root)
    project.project_dir.mkdir(parents=True)
    project.pretty_dir.mkdir(parents=True)
    project.shapes_dir.mkdir(parents=True)

    shutil.copy(DATA / "easyeda2kicad.kicad_sym", project.sym_path)
    shutil.copy(DATA / f"{FOOTPRINT}.kicad_mod", project.footprint_file)
    shutil.copy(DATA / "sym-lib-table", project.project_dir / "sym-lib-table")
    shutil.copy(DATA / "fp-lib-table", project.project_dir / "fp-lib-table")

    # Los modelos de verdad pesan 2 MB; para los tests solo importa que el
    # fichero exista y se llame como toca.
    for ext in (".wrl", ".step"):
        project.model_file(ext).write_text(f"modelo de mentira {ext}\n", encoding="utf-8")

    (project.project_dir / "CircuitoV5.kicad_pro").write_text("{}\n", encoding="utf-8")
    return project


@pytest.fixture
def project(tmp_path: Path) -> Project:
    """Proyecto completo y consistente, listo para leer o para borrar cosas."""
    return _build(tmp_path / "Instrumentacion")


@pytest.fixture
def paths(project: Project):
    """Las LibraryPaths de ese proyecto, resueltas por las lib-tables."""
    from kicadcomponent.project import resolve_library

    return resolve_library(project_dir=project.project_dir)


@pytest.fixture
def library(paths):
    from kicadcomponent.library import Library

    return Library(paths)


@pytest.fixture
def no_color(monkeypatch):
    """Desactiva los colores para poder comparar la salida tal cual."""
    monkeypatch.setenv("NO_COLOR", "1")
    from kicadcomponent import cli

    monkeypatch.setattr(cli, "style", cli.Style(False))
