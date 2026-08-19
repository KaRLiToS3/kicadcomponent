"""Tests de la interfaz de linea de comandos."""

from __future__ import annotations

import pytest

from kicadcomponent import cli
from kicadcomponent.cli import Style, _make_style, _with_default_command, fail, main

from .conftest import FOOTPRINT, LCSC, MODEL, SYMBOL


@pytest.fixture
def en(project):
    """Los argumentos comunes para trabajar sobre el proyecto de pruebas."""
    return ["--project", str(project.project_dir)]


@pytest.fixture
def sin_importar(monkeypatch):
    """Evita salir a la red: apunta las llamadas y devuelve exito."""
    llamadas = []

    def falso(lcsc_id, paths, mode="full", overwrite=True):
        llamadas.append((lcsc_id, mode, overwrite))
        return 0

    monkeypatch.setattr(cli, "import_component", falso)
    return llamadas


# -------------------------------------------------------------------- colores

def test_style_encendido_mete_ansi():
    assert Style(True).red("hola") == "\033[31mhola\033[0m"


def test_style_apagado_no_toca_el_texto():
    style = Style(False)
    assert style.red("hola") == "hola"
    assert style.green("a") == "a"
    assert style.yellow("a") == "a"
    assert style.cyan("a") == "a"
    assert style.dim("a") == "a"


def test_no_color_apaga_los_colores(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    assert not _make_style().enabled


def test_sin_terminal_tampoco_hay_colores(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False, raising=False)
    assert not _make_style().enabled


def test_fail_escribe_en_stderr_y_devuelve_1(capsys, no_color):
    assert fail("se rompio") == 1
    assert "se rompio" in capsys.readouterr().err


# --------------------------------------------------- subcomando por defecto

def test_un_lcsc_suelto_se_convierte_en_add():
    assert _with_default_command(["C12345"]) == ["add", "C12345"]


@pytest.mark.parametrize("argv", [["add", "C1"], ["list"], ["ls"], ["remove", "X"], ["rm", "X"], ["where"]])
def test_un_subcomando_explicito_se_respeta(argv):
    assert _with_default_command(argv) == argv


@pytest.mark.parametrize("bandera", ["-h", "--help", "--version"])
def test_la_ayuda_y_la_version_pasan_de_largo(bandera):
    assert _with_default_command([bandera]) == [bandera]


def test_varios_lcsc_sueltos_llevan_un_solo_add():
    assert _with_default_command(["C1", "C2"]) == ["add", "C1", "C2"]


def test_los_flags_van_detras_del_id(project, sin_importar):
    assert main(["C352847", "--3d", "--project", str(project.project_dir)]) == 0
    assert sin_importar[0][1] == "3d"


@pytest.mark.xfail(
    reason="_with_default_command mete 'add' delante del primer argumento sin guion, "
           "asi que rompe cualquier flag que vaya antes del LCSC ID",
    strict=True,
)
@pytest.mark.parametrize("argv", [["--3d", "C12345"], ["--project", "/x", "C12345"]])
def test_los_flags_deberian_poder_ir_delante_del_id(argv):
    from kicadcomponent.cli import build_parser

    build_parser().parse_args(_with_default_command(argv))


# ----------------------------------------------------------------------- main

def test_sin_argumentos_enseña_la_ayuda(capsys):
    assert main([]) == 0
    assert "usage: kicadcomponent" in capsys.readouterr().out


def test_version(capsys):
    from kicadcomponent import __version__

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_una_palabra_suelta_se_toma_por_un_lcsc_id(tmp_path, monkeypatch, capsys, no_color):
    """No hay "subcomando desconocido": lo que no es un subcomando es un ID."""
    assert _with_default_command(["inventado"]) == ["add", "inventado"]

    monkeypatch.chdir(tmp_path)  # sin ningun .kicad_pro alrededor
    assert main(["inventado"]) == 1
    assert "No se encontro ningun *.kicad_pro" in capsys.readouterr().err


def test_un_flag_inventado_sale_con_2():
    with pytest.raises(SystemExit) as exc:
        main(["list", "--inventado"])
    assert exc.value.code == 2


def test_un_proyecto_sin_libreria_da_error_controlado(tmp_path, capsys, no_color):
    (tmp_path / "x.kicad_pro").write_text("{}\n", encoding="utf-8")
    assert main(["list", "--project", str(tmp_path)]) == 1
    assert "Error:" in capsys.readouterr().err


def test_un_kicad_sym_corrupto_da_error_controlado(project, en, capsys, no_color):
    project.sym_path.write_text("(kicad_symbol_lib (symbol", encoding="utf-8")
    assert main(["list", *en]) == 1
    assert "Error:" in capsys.readouterr().err


# ---------------------------------------------------------------------- where

def test_where_enseña_las_tres_rutas(project, en, capsys, no_color):
    assert main(["where", *en]) == 0
    salida = capsys.readouterr().out
    assert str(project.sym_path) in salida
    assert str(project.pretty_dir) in salida
    assert str(project.shapes_dir) in salida


def test_where_avisa_de_lo_que_aun_no_existe(project, en, capsys, no_color):
    import shutil

    shutil.rmtree(project.shapes_dir)
    main(["where", *en])
    assert "aun no existen: modelos 3D" in capsys.readouterr().out


def test_where_admite_lib_en_vez_de_proyecto(tmp_path, capsys, no_color):
    assert main(["where", "--lib", str(tmp_path)]) == 0
    assert str(tmp_path / "easyeda2kicad.kicad_sym") in capsys.readouterr().out


def test_nickname_cambia_los_nombres_de_los_ficheros(tmp_path, capsys, no_color):
    main(["where", "--lib", str(tmp_path), "--nickname", "mislibs"])
    assert "mislibs.kicad_sym" in capsys.readouterr().out


# ----------------------------------------------------------------------- list

def test_list_saca_la_cadena_completa(en, capsys, no_color):
    assert main(["list", *en]) == 0
    salida = capsys.readouterr().out
    assert LCSC in salida
    assert SYMBOL in salida
    assert FOOTPRINT in salida
    assert MODEL in salida
    assert "1 componente en" in salida


def test_list_tiene_alias_ls(en, capsys, no_color):
    assert main(["ls", *en]) == 0
    assert SYMBOL in capsys.readouterr().out


def test_list_avisa_si_la_libreria_esta_vacia(project, en, capsys, no_color):
    project.sym_path.unlink()
    assert main(["list", *en]) == 0
    assert "no tiene simbolos todavia" in capsys.readouterr().out


# ------------------------------------------------------------------------ add

def test_add_llama_al_importador(en, sin_importar, capsys):
    assert main(["add", "C352847", *en]) == 0
    assert sin_importar == [("C352847", "full", True)]


def test_add_admite_varios_ids(en, sin_importar):
    assert main(["add", "C1", "C2", "C3", *en]) == 0
    assert [c[0] for c in sin_importar] == ["C1", "C2", "C3"]


@pytest.mark.parametrize(
    "bandera, modo",
    [("--symbol", "symbol"), ("--footprint", "footprint"), ("--3d", "3d")],
)
def test_add_tiene_atajos_para_cada_modo(en, sin_importar, bandera, modo):
    main(["add", "C1", bandera, *en])
    assert sin_importar[0][1] == modo


def test_add_admite_mode_explicito(en, sin_importar):
    main(["add", "C1", "--mode", "footprint", *en])
    assert sin_importar[0][1] == "footprint"


def test_add_no_overwrite(en, sin_importar):
    main(["add", "C1", "--no-overwrite", *en])
    assert sin_importar[0][2] is False


def test_add_devuelve_1_si_falla_alguno(en, monkeypatch, capsys, no_color):
    monkeypatch.setattr(cli, "import_component", lambda *a, **k: 2)
    assert main(["add", "C1", *en]) == 1
    assert "devolvio 2" in capsys.readouterr().err


def test_add_sigue_con_los_demas_aunque_uno_falle(en, monkeypatch):
    vistos = []

    def falso(lcsc_id, paths, mode="full", overwrite=True):
        vistos.append(lcsc_id)
        return 1 if lcsc_id == "C1" else 0

    monkeypatch.setattr(cli, "import_component", falso)
    assert main(["add", "C1", "C2", *en]) == 1
    assert vistos == ["C1", "C2"]


def test_la_primera_importacion_necesita_lib(tmp_path, sin_importar, capsys, no_color):
    """Sin entrada en las lib-tables no hay libreria que resolver todavia."""
    (tmp_path / "x.kicad_pro").write_text("{}\n", encoding="utf-8")
    assert main(["add", "C1", "--project", str(tmp_path)]) == 1
    assert sin_importar == []

    destino = tmp_path / "lib"
    assert main(["add", "C1", "--lib", str(destino)]) == 0
    assert sin_importar == [("C1", "full", True)]


# --------------------------------------------------------------------- remove

def test_remove_borra_la_cadena_entera(project, en, capsys, no_color):
    assert main(["remove", LCSC, "-y", *en]) == 0
    assert not project.footprint_file.exists()
    assert not project.model_file(".wrl").exists()
    assert SYMBOL not in project.sym_path.read_text(encoding="utf-8")


def test_remove_tiene_alias_rm(project, en, no_color):
    assert main(["rm", LCSC, "-y", *en]) == 0
    assert not project.footprint_file.exists()


def test_dry_run_enseña_el_plan_sin_tocar_nada(project, en, capsys, no_color):
    assert main(["remove", LCSC, "--dry-run", *en]) == 0
    salida = capsys.readouterr().out
    assert "Se va a borrar" in salida
    assert "no se ha tocado nada" in salida
    assert project.footprint_file.exists()
    assert SYMBOL in project.sym_path.read_text(encoding="utf-8")


def test_pide_confirmacion_y_obedece_al_si(project, en, monkeypatch, no_color):
    monkeypatch.setattr("builtins.input", lambda _: "s")
    assert main(["remove", LCSC, *en]) == 0
    assert not project.footprint_file.exists()


@pytest.mark.parametrize("respuesta", ["n", "", "no", "cualquier cosa"])
def test_una_respuesta_que_no_sea_si_cancela(project, en, monkeypatch, respuesta, capsys, no_color):
    monkeypatch.setattr("builtins.input", lambda _: respuesta)
    assert main(["remove", LCSC, *en]) == 1
    assert "Cancelado" in capsys.readouterr().out
    assert project.footprint_file.exists()


@pytest.mark.parametrize("respuesta", ["y", "yes", "s", "si", "sí", "  Y  "])
def test_todas_las_formas_de_decir_que_si(project, en, monkeypatch, respuesta, no_color):
    monkeypatch.setattr("builtins.input", lambda _: respuesta)
    assert main(["remove", LCSC, *en]) == 0


def test_un_ctrl_d_cancela(project, en, monkeypatch, capsys, no_color):
    def corta(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", corta)
    assert main(["remove", LCSC, *en]) == 1
    assert project.footprint_file.exists()


def test_remove_dice_donde_quedo_la_copia(project, en, capsys, no_color):
    main(["remove", LCSC, "-y", *en])
    assert "copia en" in capsys.readouterr().out
    assert project.sym_path.with_suffix(".kicad_sym.bak").exists()


def test_remove_avisa_de_refrescar_kicad(en, capsys, no_color):
    main(["remove", LCSC, "-y", *en])
    assert "Refresca las librerias en KiCad" in capsys.readouterr().out


def test_remove_explica_que_no_encuentra_nada(en, capsys, no_color):
    assert main(["remove", "no_existe", *en]) == 1
    err = capsys.readouterr().err
    assert "No hay ningun componente" in err
    assert "kicadcomponent list" in err


def test_remove_enseña_los_candidatos_si_hay_duda(project, en, capsys, no_color):
    from .test_library import _add_symbol

    _add_symbol(project, "LM324N_OTRO", "C999", "easyeda2kicad:OTRO")
    assert main(["remove", "LM324", *en]) == 1
    err = capsys.readouterr().err
    assert "encaja con varios" in err
    assert "LM324N_OTRO" in err


def test_remove_enseña_las_notas_del_plan(project, en, capsys, no_color):
    from .test_library import _add_symbol

    _add_symbol(project, "COMPARTE_FOOTPRINT", "C999", f"easyeda2kicad:{FOOTPRINT}")
    main(["remove", LCSC, "--dry-run", *en])
    assert "nota:" in capsys.readouterr().out
