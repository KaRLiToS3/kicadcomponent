"""Tests del inventario y del borrado."""

from __future__ import annotations

import pytest

from kicadcomponent.library import (
    AmbiguousQuery,
    Component,
    ComponentNotFound,
    Library,
    LibraryError,
    RemovalPlan,
    _model_name,
    _properties,
)
from kicadcomponent.sexpr import parse

from .conftest import FOOTPRINT, LCSC, MODEL, SYMBOL


# ------------------------------------------------------------------ utilidades

def _add_symbol(project, name, lcsc, footprint):
    """Mete otro simbolo en el .kicad_sym, en el estilo de easyeda2kicad."""
    texto = project.sym_path.read_text(encoding="utf-8")
    bloque = (
        f'\n  (symbol "{name}"\n'
        '    (property\n      "Reference"\n      "U"\n      (id 0)\n    )\n'
        f'    (property\n      "Footprint"\n      "{footprint}"\n      (id 2)\n    )\n'
        f'    (property\n      "LCSC Part"\n      "{lcsc}"\n      (id 6)\n    )\n'
        '  )\n'
    )
    corte = texto.rfind(")")
    project.sym_path.write_text(texto[:corte] + bloque + texto[corte:], encoding="utf-8")


def _add_footprint(project, name, model=None):
    """Crea un .kicad_mod suelto, opcionalmente apuntando a un modelo 3D."""
    cuerpo = f'(module easyeda2kicad:{name} (layer F.Cu)\n'
    if model:
        cuerpo += f'\t(model "/home/otro/kicad/lib/easyeda2kicad.3dshapes/{model}.wrl"\n\t)\n'
    cuerpo += ")\n"
    (project.pretty_dir / f"{name}.kicad_mod").write_text(cuerpo, encoding="utf-8")


# ----------------------------------------------------------------- _model_name

@pytest.mark.parametrize(
    "referencia, esperado",
    [
        ("/home/otro/lib/MODELO.wrl", "MODELO"),
        ("/home/otro/lib/MODELO.step", "MODELO"),
        ("/home/otro/lib/MODELO.stp", "MODELO"),
        ("MODELO.WRL", "MODELO"),
        (r"C:\Users\otro\lib\MODELO.wrl", "MODELO"),
        ("${KIPRJMOD}/lib/MODELO.wrl", "MODELO"),
        ("MODELO", "MODELO"),
        ("MODELO.desconocida", "MODELO.desconocida"),
        ("PDIP-14_L19.7-W6.6-H5.1.wrl", "PDIP-14_L19.7-W6.6-H5.1"),
    ],
)
def test_model_name_saca_el_nombre_venga_como_venga(referencia, esperado):
    assert _model_name(referencia) == esperado


# ----------------------------------------------------------------- _properties

def test_properties_lee_el_estilo_de_easyeda2kicad(project):
    root = parse(project.sym_path.read_text(encoding="utf-8"))
    symbol, = root.find("symbol")
    props = _properties(symbol)
    assert props["LCSC Part"] == LCSC
    assert props["Footprint"] == f"easyeda2kicad:{FOOTPRINT}"
    assert props["Manufacturer"] == "TI(德州仪器)"


def test_properties_lee_tambien_el_estilo_del_editor_de_kicad():
    from .conftest import DATA

    root = parse((DATA / "LM358P.kicad_sym").read_text(encoding="utf-8"))
    symbol, = root.find("symbol")
    props = _properties(symbol)
    assert props["Reference"] == "U"
    assert props["Footprint"] == "LM358P:DIP794W45P254L959H508Q8"


# -------------------------------------------------------------------- lectura

def test_lee_el_componente_del_fichero_real(library):
    component, = library.components
    assert component.name == SYMBOL
    assert component.lcsc == LCSC
    assert component.footprint == FOOTPRINT
    assert component.footprint_lib == "easyeda2kicad"


def test_una_libreria_que_aun_no_existe_esta_vacia(paths, project):
    project.sym_path.unlink()
    assert Library(paths).components == []


def test_un_kicad_sym_corrupto_da_un_error_con_la_ruta(paths, project):
    project.sym_path.write_text("(kicad_symbol_lib (symbol", encoding="utf-8")
    with pytest.raises(LibraryError, match="no se puede leer"):
        Library(paths).components


def test_el_footprint_sin_libreria_delante_se_lee_igual(paths, project):
    _add_symbol(project, "PELADO", "C1", "SIN_LIB")
    component = next(c for c in Library(paths).components if c.name == "PELADO")
    assert component.footprint == "SIN_LIB"
    assert component.footprint_lib is None


def test_se_relee_solo_una_vez(library):
    assert library.components is library.components


# ------------------------------------------------------------------ footprints

def test_footprint_names_lista_lo_que_hay_en_el_pretty(library):
    assert library.footprint_names() == [FOOTPRINT]


def test_footprint_names_vacio_si_no_hay_carpeta(paths, project):
    import shutil

    shutil.rmtree(project.pretty_dir)
    assert Library(paths).footprint_names() == []


def test_footprint_file_compone_la_ruta(library, project):
    assert library.footprint_file(FOOTPRINT) == project.footprint_file


# ------------------------------------------------------------------ modelos 3D

def test_el_modelo_no_se_llama_como_el_footprint(library):
    """El caso que justifica model_for(): easyeda2kicad mete un H5.1 de mas."""
    assert library.model_for(FOOTPRINT) == MODEL
    assert MODEL != FOOTPRINT


def test_model_for_es_none_si_el_footprint_no_existe(library):
    assert library.model_for("NO_EXISTE") is None


def test_model_for_es_none_si_el_kicad_mod_no_tiene_modelo(library, project):
    _add_footprint(project, "SIN_MODELO")
    assert library.model_for("SIN_MODELO") is None


def test_model_for_aguanta_un_kicad_mod_corrupto(library, project):
    (project.pretty_dir / "ROTO.kicad_mod").write_text("(module (", encoding="utf-8")
    assert library.model_for("ROTO") is None


def test_model_files_encuentra_las_dos_extensiones(library, project):
    assert set(library.model_files(MODEL)) == {
        project.model_file(".wrl"),
        project.model_file(".step"),
    }


def test_model_files_vacio_si_no_hay_nada(library):
    assert library.model_files("INVENTADO") == []


def test_footprints_using_model_encuentra_a_los_demas(library, project):
    _add_footprint(project, "OTRO_FP", model=MODEL)
    assert library.footprints_using_model(MODEL, skip=FOOTPRINT) == ["OTRO_FP"]


def test_footprints_using_model_se_salta_el_indicado(library):
    assert library.footprints_using_model(MODEL, skip=FOOTPRINT) == []


# -------------------------------------------------------------------- busqueda

@pytest.mark.parametrize("consulta", [LCSC, LCSC.lower(), f"  {LCSC}  "])
def test_busca_por_lcsc(library, consulta):
    assert library.find(consulta).name == SYMBOL


@pytest.mark.parametrize("consulta", [SYMBOL, SYMBOL.lower()])
def test_busca_por_nombre_de_simbolo(library, consulta):
    assert library.find(consulta).lcsc == LCSC


def test_busca_por_trozo_del_nombre(library):
    assert library.find("LM324").name == SYMBOL


def test_devuelve_none_si_no_encaja_nada(library):
    assert library.find("nada_de_nada") is None


def test_el_nombre_exacto_gana_al_parcial(paths, project):
    _add_symbol(project, "LM324N_NOPB_V2", "C999", "easyeda2kicad:OTRO")
    assert Library(paths).find(SYMBOL).name == SYMBOL


def test_protesta_si_la_consulta_encaja_con_varios(paths, project):
    _add_symbol(project, "LM324N_OTRO", "C999", "easyeda2kicad:OTRO")
    with pytest.raises(AmbiguousQuery) as exc:
        Library(paths).find("LM324")
    assert len(exc.value.candidates) == 2
    assert exc.value.query == "LM324"


# ---------------------------------------------------------------- plan_removal

def test_el_plan_resuelve_la_cadena_entera(library, project):
    plan = library.plan_removal(LCSC)
    assert plan.symbol == SYMBOL
    assert plan.lcsc == LCSC
    assert plan.footprint == FOOTPRINT
    assert plan.model == MODEL
    assert set(plan.delete) == {
        project.footprint_file,
        project.model_file(".wrl"),
        project.model_file(".step"),
    }
    assert not plan.is_empty


def test_no_borra_un_footprint_que_usa_otro_simbolo(paths, project):
    _add_symbol(project, "OTRO_QUE_LO_COMPARTE", "C999", f"easyeda2kicad:{FOOTPRINT}")
    plan = Library(paths).plan_removal(LCSC)
    assert project.footprint_file not in plan.delete
    assert any("se conserva" in nota for nota in plan.notes)


def test_si_el_footprint_se_queda_el_modelo_tambien(paths, project):
    _add_symbol(project, "OTRO_QUE_LO_COMPARTE", "C999", f"easyeda2kicad:{FOOTPRINT}")
    plan = Library(paths).plan_removal(LCSC)
    assert plan.delete == []
    assert any("modelo 3D se conserva" in nota for nota in plan.notes)


def test_no_borra_un_modelo_que_usa_otro_footprint(library, project):
    _add_footprint(project, "OTRO_FP", model=MODEL)
    plan = library.plan_removal(LCSC)
    assert plan.delete == [project.footprint_file]
    assert any("lo usan tambien" in nota for nota in plan.notes)


def test_no_toca_un_footprint_de_otra_libreria(paths, project):
    _add_symbol(project, "AJENO", "C777", "Device:R_Small")
    plan = Library(paths).plan_removal("C777")
    assert plan.delete == []
    assert any("vive en la libreria 'Device'" in nota for nota in plan.notes)


def test_avisa_si_el_fichero_del_footprint_ya_no_esta(library, project):
    project.footprint_file.unlink()
    plan = library.plan_removal(LCSC)
    assert plan.delete == []
    assert any("ya no existe" in nota for nota in plan.notes)


def test_borra_un_footprint_suelto_sin_simbolo(library, project):
    _add_footprint(project, "SUELTO")
    plan = library.plan_removal("SUELTO")
    assert plan.symbol == ""
    assert plan.footprint == "SUELTO"
    assert plan.delete == [project.pretty_dir / "SUELTO.kicad_mod"]
    assert not plan.is_empty


def test_protesta_si_no_encuentra_nada_que_borrar(library):
    with pytest.raises(ComponentNotFound, match="ningun componente encaja"):
        library.plan_removal("no_existe_ni_de_lejos")


def test_protesta_si_varios_footprints_sueltos_encajan(library, project):
    _add_footprint(project, "SUELTO_A")
    _add_footprint(project, "SUELTO_B")
    with pytest.raises(AmbiguousQuery) as exc:
        library.plan_removal("SUELTO")
    assert len(exc.value.candidates) == 2


def test_un_plan_recien_hecho_esta_vacio():
    assert RemovalPlan().is_empty


# ----------------------------------------------------------------------- apply

def test_apply_borra_los_ficheros_y_el_simbolo(library, project):
    plan = library.plan_removal(LCSC)
    library.apply(plan)

    assert not project.footprint_file.exists()
    assert not project.model_file(".wrl").exists()
    assert not project.model_file(".step").exists()
    assert library.components == []


def test_apply_deja_copia_de_seguridad_del_kicad_sym(library, project):
    original = project.sym_path.read_text(encoding="utf-8")
    backup = library.apply(library.plan_removal(LCSC))

    assert backup == project.sym_path.with_suffix(".kicad_sym.bak")
    assert backup.read_text(encoding="utf-8") == original


def test_sin_simbolo_que_borrar_no_hay_copia(library, project):
    _add_footprint(project, "SUELTO")
    assert library.apply(library.plan_removal("SUELTO")) is None


def test_el_resto_del_fichero_no_se_toca(paths, project):
    """Se borra recortando texto, asi que lo demas tiene que quedar identico."""
    _add_symbol(project, "SUPERVIVIENTE", "C999", "easyeda2kicad:OTRO")
    library = Library(paths)
    antes = project.sym_path.read_text(encoding="utf-8")
    superviviente = next(c for c in library.components if c.name == "SUPERVIVIENTE")
    bloque_intacto = antes[superviviente.start:superviviente.end]

    library.apply(library.plan_removal(LCSC))
    despues = project.sym_path.read_text(encoding="utf-8")

    assert bloque_intacto in despues
    assert despues.startswith("(kicad_symbol_lib")
    assert "(generator https://github.com/uPesy/easyeda2kicad.py)" in despues
    assert SYMBOL not in despues


def test_lo_que_queda_sigue_siendo_un_kicad_sym_valido(library, project):
    library.apply(library.plan_removal(LCSC))
    root = parse(project.sym_path.read_text(encoding="utf-8"))
    assert root.head == "kicad_symbol_lib"
    assert list(root.find("symbol")) == []


def test_no_deja_lineas_en_blanco_donde_estaba_el_simbolo(paths, project):
    _add_symbol(project, "SUPERVIVIENTE", "C999", "easyeda2kicad:OTRO")
    library = Library(paths)
    library.apply(library.plan_removal(LCSC))
    texto = project.sym_path.read_text(encoding="utf-8")
    assert "\n  \n" not in texto


def test_borrar_un_simbolo_que_no_existe_protesta(library):
    with pytest.raises(LibraryError, match="no existe el simbolo"):
        library._remove_symbol("FANTASMA")


def test_component_tiene_repr_util():
    assert "R" in repr(Component("R", "C1", "FP", None, 0, 1))
