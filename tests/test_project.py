"""Tests de la localizacion del proyecto y de la libreria."""

from __future__ import annotations

from pathlib import Path

import pytest

from kicadcomponent.project import (
    DEFAULT_NICKNAME,
    LibraryPaths,
    ProjectError,
    _expand,
    _read_lib_table,
    find_project,
    resolve_library,
)

from .conftest import DATA


# -------------------------------------------------------------- find_project

def test_encuentra_el_proyecto_en_el_directorio_actual(project):
    assert find_project(project.project_dir) == project.project_dir.resolve()


def test_sube_hasta_encontrar_el_kicad_pro(project):
    hondo = project.project_dir / "a" / "b" / "c"
    hondo.mkdir(parents=True)
    assert find_project(hondo) == project.project_dir.resolve()


def test_baja_si_no_hay_nada_por_encima(project):
    """Estar en la raiz del repo con el proyecto en una subcarpeta es lo normal."""
    assert find_project(project.root) == project.project_dir.resolve()


def test_usa_el_directorio_actual_si_no_se_le_dice_otra_cosa(project, monkeypatch):
    monkeypatch.chdir(project.project_dir)
    assert find_project() == project.project_dir.resolve()


def test_se_niega_a_elegir_si_hay_varios_proyectos(project):
    otro = project.root / "OtroCircuito"
    otro.mkdir()
    (otro / "OtroCircuito.kicad_pro").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ProjectError, match="varios proyectos"):
        find_project(project.root)


def test_falla_con_un_mensaje_util_si_no_hay_ninguno(tmp_path):
    with pytest.raises(ProjectError, match="No se encontro ningun"):
        find_project(tmp_path)


def test_no_baja_mas_alla_del_limite(tmp_path):
    hondo = tmp_path / "a" / "b" / "c" / "d" / "e"
    hondo.mkdir(parents=True)
    (hondo / "x.kicad_pro").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ProjectError, match="No se encontro ningun"):
        find_project(tmp_path)


# ------------------------------------------------------------------- _expand

def test_expand_resuelve_kiprjmod(tmp_path):
    resultado = _expand("${KIPRJMOD}/../lib/easyeda2kicad", tmp_path / "v1")
    assert resultado == tmp_path / "lib" / "easyeda2kicad"


def test_expand_admite_tambien_la_forma_con_parentesis(tmp_path):
    assert _expand("$(KIPRJMOD)/lib", tmp_path) == tmp_path / "lib"


def test_expand_resuelve_variables_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_LIB", str(tmp_path / "compartida"))
    assert _expand("${MI_LIB}/easyeda2kicad", tmp_path) == tmp_path / "compartida" / "easyeda2kicad"


def test_expand_deja_las_rutas_absolutas_como_estan(tmp_path):
    assert _expand(str(tmp_path / "abs"), tmp_path / "otro") == tmp_path / "abs"


def test_expand_cuelga_las_relativas_del_proyecto(tmp_path):
    assert _expand("lib/easyeda2kicad", tmp_path) == tmp_path / "lib" / "easyeda2kicad"


def test_expand_resuelve_la_virgulilla(tmp_path):
    assert _expand("~/kicad", tmp_path) == Path.home() / "kicad"


# ------------------------------------------------------------ _read_lib_table

def test_lee_la_uri_de_una_lib_table_de_verdad(project):
    uri = _read_lib_table(
        project.project_dir / "sym-lib-table", DEFAULT_NICKNAME, project.project_dir
    )
    assert uri == project.sym_path


def test_elige_la_libreria_por_nombre_entre_varias(project):
    """El fp-lib-table real tiene dos: 'footprints' y 'easyeda2kicad'."""
    uri = _read_lib_table(
        project.project_dir / "fp-lib-table", "footprints", project.project_dir
    )
    assert uri == project.root / "lib" / "footprints.pretty"


def test_devuelve_none_si_el_nickname_no_esta(project):
    assert _read_lib_table(
        project.project_dir / "sym-lib-table", "no_existe", project.project_dir
    ) is None


def test_devuelve_none_si_el_fichero_no_existe(tmp_path):
    assert _read_lib_table(tmp_path / "sym-lib-table", DEFAULT_NICKNAME, tmp_path) is None


def test_devuelve_none_si_la_tabla_esta_corrupta(tmp_path):
    tabla = tmp_path / "sym-lib-table"
    tabla.write_text("(sym_lib_table (lib (name ", encoding="utf-8")
    assert _read_lib_table(tabla, DEFAULT_NICKNAME, tmp_path) is None


# ---------------------------------------------------------- resolve_library

def test_resuelve_las_tres_rutas_desde_las_lib_tables(project):
    paths = resolve_library(project_dir=project.project_dir)
    assert paths.nickname == DEFAULT_NICKNAME
    assert paths.sym_path == project.sym_path
    assert paths.pretty_dir == project.pretty_dir
    assert paths.shapes_dir == project.shapes_dir
    assert paths.project_dir == project.project_dir.resolve()


def test_la_libreria_puede_vivir_fuera_de_la_carpeta_del_proyecto(project):
    """Es el caso real: ${KIPRJMOD}/../lib/, compartida entre v1/ y v2/."""
    paths = resolve_library(project_dir=project.project_dir)
    assert project.project_dir not in paths.sym_path.parents


def test_lib_se_salta_las_tablas(project, tmp_path):
    suelta = tmp_path / "suelta"
    paths = resolve_library(lib_root=suelta, nickname="otra")
    assert paths.sym_path == suelta / "otra.kicad_sym"
    assert paths.pretty_dir == suelta / "otra.pretty"
    assert paths.shapes_dir == suelta / "otra.3dshapes"


def test_deduce_los_footprints_si_solo_esta_el_sym_lib_table(project):
    (project.project_dir / "fp-lib-table").unlink()
    paths = resolve_library(project_dir=project.project_dir)
    assert paths.pretty_dir == project.pretty_dir


def test_deduce_los_simbolos_si_solo_esta_el_fp_lib_table(project):
    (project.project_dir / "sym-lib-table").unlink()
    paths = resolve_library(project_dir=project.project_dir)
    assert paths.sym_path == project.sym_path
    assert paths.shapes_dir == project.shapes_dir


def test_falla_si_el_proyecto_no_declara_la_libreria(project):
    with pytest.raises(ProjectError, match="no declara ninguna libreria"):
        resolve_library(project_dir=project.project_dir, nickname="inventada")


def test_falla_si_no_hay_ninguna_lib_table(project):
    (project.project_dir / "sym-lib-table").unlink()
    (project.project_dir / "fp-lib-table").unlink()
    with pytest.raises(ProjectError, match="no declara ninguna libreria"):
        resolve_library(project_dir=project.project_dir)


# -------------------------------------------------------------- LibraryPaths

def test_output_base_es_lo_que_espera_easyeda2kicad(paths):
    """easyeda2kicad --output quiere la ruta sin extension."""
    assert paths.output_base.name == "easyeda2kicad"
    assert paths.output_base.suffix == ""


def test_root_es_la_carpeta_de_la_libreria(paths, project):
    assert paths.root == project.lib_dir


def test_describe_enseña_las_tres_rutas(paths):
    texto = paths.describe()
    assert str(paths.sym_path) in texto
    assert str(paths.pretty_dir) in texto
    assert str(paths.shapes_dir) in texto


def test_las_lib_tables_de_ejemplo_son_las_reales():
    """Si alguien regenera los fixtures, que salte aqui y no en un test raro."""
    assert "${KIPRJMOD}/../lib/easyeda2kicad" in (DATA / "sym-lib-table").read_text(
        encoding="utf-8"
    )
