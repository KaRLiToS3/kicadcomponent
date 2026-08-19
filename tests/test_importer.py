"""Tests del envoltorio sobre easyeda2kicad."""

from __future__ import annotations

import pytest

from kicadcomponent.importer import MODES, build_args, import_component


@pytest.fixture
def easyeda(monkeypatch):
    """Sustituye el main() de easyeda2kicad y apunta con que se le llamo."""
    llamadas = []

    def falso(args):
        llamadas.append(args)
        return 0

    monkeypatch.setattr("easyeda2kicad.__main__.main", falso)
    return llamadas


# ---------------------------------------------------------------- build_args

@pytest.mark.parametrize("modo, opcion", sorted(MODES.items()))
def test_cada_modo_se_traduce_a_su_opcion(paths, modo, opcion):
    assert build_args("C352847", paths, modo, overwrite=False)[0] == opcion


def test_los_argumentos_llevan_el_id_y_la_salida(paths):
    args = build_args("C352847", paths, "full", overwrite=False)
    assert "--lcsc_id=C352847" in args
    assert f"--output={paths.output_base}" in args


def test_la_salida_va_sin_extension(paths):
    """easyeda2kicad le pega el .kicad_sym, el .pretty y el .3dshapes."""
    salida = [a for a in build_args("C1", paths, "full", False) if a.startswith("--output=")][0]
    assert not salida.endswith(".kicad_sym")
    assert salida.endswith("easyeda2kicad")


def test_overwrite_se_añade_solo_cuando_toca(paths):
    assert "--overwrite" in build_args("C1", paths, "full", overwrite=True)
    assert "--overwrite" not in build_args("C1", paths, "full", overwrite=False)


def test_un_modo_inventado_protesta(paths):
    with pytest.raises(ValueError, match="modo desconocido"):
        build_args("C1", paths, "holograma", overwrite=True)


# ----------------------------------------------------------- import_component

def test_llama_a_easyeda2kicad_con_los_argumentos_construidos(paths, easyeda):
    import_component("C352847", paths, mode="3d", overwrite=True)
    args, = easyeda
    assert args == ["--3d", "--lcsc_id=C352847", f"--output={paths.output_base}", "--overwrite"]


def test_crea_la_carpeta_de_la_libreria_si_no_existe(paths, project, easyeda):
    import shutil

    shutil.rmtree(project.lib_dir)
    import_component("C352847", paths)
    assert paths.root.is_dir()


def test_devuelve_el_codigo_de_easyeda2kicad(paths, monkeypatch):
    monkeypatch.setattr("easyeda2kicad.__main__.main", lambda args: 3)
    assert import_component("C1", paths) == 3


def test_un_none_cuenta_como_exito(paths, monkeypatch):
    monkeypatch.setattr("easyeda2kicad.__main__.main", lambda args: None)
    assert import_component("C1", paths) == 0


@pytest.mark.parametrize(
    "codigo, esperado",
    [(2, 2), (0, 0), (None, 0), ("un mensaje de error", 1)],
)
def test_el_systemexit_de_argparse_se_convierte_en_codigo(paths, monkeypatch, codigo, esperado):
    """easyeda2kicad usa argparse por dentro: ante un argumento malo sale por SystemExit."""

    def revienta(args):
        raise SystemExit(codigo)

    monkeypatch.setattr("easyeda2kicad.__main__.main", revienta)
    assert import_component("C1", paths) == esperado


def test_el_modo_por_defecto_es_full(paths, easyeda):
    import_component("C1", paths)
    assert easyeda[0][0] == "--full"


def test_por_defecto_sobrescribe(paths, easyeda):
    import_component("C1", paths)
    assert "--overwrite" in easyeda[0]
