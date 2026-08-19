"""Tests del lector de s-expressions."""

from __future__ import annotations

import pytest

from kicadcomponent.sexpr import Atom, Node, ParseError, parse, tokenize

from .conftest import DATA, FOOTPRINT


# ------------------------------------------------------------------ tokenize

def test_tokenize_distingue_cadenas_de_simbolos():
    kinds = [(kind, value) for kind, _, value in tokenize('(at 0 "texto")')]
    assert kinds == [
        ("(", "("),
        ("sym", "at"),
        ("sym", "0"),
        ("str", "texto"),
        (")", ")"),
    ]


def test_tokenize_guarda_la_posicion_de_cada_token():
    tokens = list(tokenize('  (a "b")'))
    assert [offset for _, offset, _ in tokens] == [2, 3, 5, 8]


def test_tokenize_interpreta_los_escapes():
    texto = '"comilla \\" y barra \\\\"'
    (_, _, value), = [t for t in tokenize(texto) if t[0] == "str"]
    assert value == 'comilla " y barra \\'


def test_tokenize_no_parte_los_atomos_por_guiones_ni_puntos():
    values = [v for k, _, v in tokenize("(a PDIP-14_L19.7-W6.6 b)") if k == "sym"]
    assert "PDIP-14_L19.7-W6.6" in values


def test_tokenize_cadena_sin_cerrar():
    with pytest.raises(ParseError, match="sin cerrar"):
        list(tokenize('(a "sin final'))


# --------------------------------------------------------------------- parse

def test_parse_arbol_basico():
    root = parse('(kicad_symbol_lib (version 20211014) (symbol "R"))')
    assert root.head == "kicad_symbol_lib"
    assert [n.head for n in root.lists()] == ["version", "symbol"]


def test_parse_ignora_lo_que_haya_antes_del_primer_parentesis():
    root = parse('\n\n; un comentario suelto\n(a 1)')
    assert root.head == "a"


@pytest.mark.parametrize(
    "texto, mensaje",
    [
        ("", "no se encontro"),
        ("   \n  ", "no se encontro"),
        ("sin parentesis", "no se encontro"),
        ("(a (b c)", "sin cerrar"),
        ('(a "b)', "sin cerrar"),
    ],
)
def test_parse_rechaza_lo_que_no_es_valido(texto, mensaje):
    with pytest.raises(ParseError, match=mensaje):
        parse(texto)


def test_parse_para_en_el_nodo_raiz_y_no_mira_mas_alla():
    # El `break` al cerrar la raiz hace que sobre lo que venga detras.
    root = parse("(a) (b) basura")
    assert root.head == "a"


# ----------------------------------------------------------------- navegacion

def test_head_es_none_si_la_lista_empieza_por_otra_lista():
    root = parse("((a) b)")
    assert root.head is None


def test_head_es_none_en_lista_vacia():
    assert parse("()").head is None


def test_values_solo_devuelve_atomos_directos():
    root = parse('(property "Reference" "U" (id 0) (at 0 12.7 0))')
    assert root.values() == ["property", "Reference", "U"]


def test_lists_solo_devuelve_sublistas():
    root = parse('(property "Reference" "U" (id 0) (at 0 12.7 0))')
    assert [n.head for n in root.lists()] == ["id", "at"]


def test_find_no_baja_de_nivel_y_find_deep_si():
    root = parse('(symbol (property "a" "1") (sub (property "b" "2")))')
    assert len(list(root.find("property"))) == 1
    assert len(list(root.find_deep("property"))) == 2


def test_find_devuelve_vacio_si_no_hay_nada():
    assert list(parse("(a)").find("inexistente")) == []


def test_atom_marca_si_venia_entrecomillado():
    root = parse('(a "entrecomillado" pelado)')
    atoms = [it for it in root.items if isinstance(it, Atom)]
    assert [(a.value, a.quoted) for a in atoms] == [
        ("a", False),
        ("entrecomillado", True),
        ("pelado", False),
    ]


# ------------------------------------------------- posiciones (lo que importa)

def test_las_posiciones_recortan_el_texto_original_exacto():
    """El borrado es un corte de cadena, asi que start/end tienen que ser exactos."""
    texto = '(root (uno 1) (dos 2))'
    uno, dos = parse(texto).lists()
    assert texto[uno.start:uno.end] == "(uno 1)"
    assert texto[dos.start:dos.end] == "(dos 2)"


def test_las_posiciones_siguen_siendo_exactas_en_un_fichero_de_verdad():
    texto = (DATA / "easyeda2kicad.kicad_sym").read_text(encoding="utf-8")
    root = parse(texto)
    symbol, = root.find("symbol")

    recorte = texto[symbol.start:symbol.end]
    assert recorte.startswith('(symbol "LM324N_NOPB"')
    assert recorte.endswith(")")
    # Parentesis equilibrados: la prueba de que el recorte no se pasa ni se queda corto.
    assert recorte.count("(") == recorte.count(")")


def test_quitar_un_nodo_por_posicion_deja_el_resto_intacto():
    texto = "(root\n  (uno 1)\n  (dos 2)\n)"
    uno = next(parse(texto).find("uno"))
    assert texto[:uno.start] + texto[uno.end:] == "(root\n  \n  (dos 2)\n)"


# ------------------------------------------------- los dos estilos conviven

@pytest.mark.parametrize("fichero", ["easyeda2kicad.kicad_sym", "LM358P.kicad_sym"])
def test_los_dos_estilos_de_escritura_se_leen_igual(fichero):
    """easyeda2kicad parte las propiedades en varias lineas; KiCad no."""
    root = parse((DATA / fichero).read_text(encoding="utf-8"))
    symbol, = root.find("symbol")
    props = {
        p.values()[1]: p.values()[2]
        for p in symbol.find("property")
        if len(p.values()) >= 3
    }
    assert "Reference" in props
    assert props["Footprint"].endswith(
        FOOTPRINT if fichero.startswith("easyeda") else "DIP794W45P254L959H508Q8"
    )


def test_lee_texto_no_ascii():
    root = parse((DATA / "easyeda2kicad.kicad_sym").read_text(encoding="utf-8"))
    valores = [a.value for n in root.find_deep("property") for a in n.items if isinstance(a, Atom)]
    assert "TI(德州仪器)" in valores


def test_el_kicad_mod_real_tambien_se_lee():
    texto = (DATA / f"{FOOTPRINT}.kicad_mod").read_text(encoding="utf-8")
    root = parse(texto)
    assert root.head == "module"
    model, = root.find_deep("model")
    assert model.values()[1].endswith(".wrl")


def test_node_y_atom_tienen_repr_util():
    root = parse('(a "b")')
    assert "a" in repr(root)
    assert isinstance(root, Node)
    atom = root.items[0]
    assert "a" in repr(atom)
