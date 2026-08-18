"""Lector minimo de s-expressions de KiCad.

Sólo se necesita leer y recortar, nunca reescribir: cada nodo guarda su
posicion exacta en el texto original, asi que borrar un bloque es cortar un
trozo de cadena y el resto del fichero queda byte a byte igual.

Hace falta un parser de verdad (y no expresiones regulares) porque en un mismo
`.kicad_sym` conviven dos estilos de escritura:

    easyeda2kicad          KiCad al guardar desde el editor
    (property              (property "Reference" "R"
      "Reference"
      "R"
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Tuple, Union

_WHITESPACE = " \t\r\n"
_ATOM_END = ' \t\r\n()"'


class Atom:
    """Un valor suelto. `quoted` distingue `"texto"` de un simbolo pelado."""

    __slots__ = ("value", "quoted", "start")

    def __init__(self, value: str, quoted: bool, start: int) -> None:
        self.value = value
        self.quoted = quoted
        self.start = start

    def __repr__(self) -> str:  # pragma: no cover - solo para depurar
        return f"Atom({self.value!r})"


class Node:
    """Una lista `(...)` con sus posiciones de apertura y cierre."""

    __slots__ = ("items", "start", "end")

    def __init__(self, items: List["Element"], start: int, end: int) -> None:
        self.items = items
        self.start = start
        self.end = end

    @property
    def head(self) -> Optional[str]:
        """Nombre de la lista: la `symbol` de `(symbol "X" ...)`."""
        first = self.items[0] if self.items else None
        return first.value if isinstance(first, Atom) else None

    def values(self) -> List[str]:
        """Atomos directos, sin entrar en las sublistas."""
        return [it.value for it in self.items if isinstance(it, Atom)]

    def lists(self) -> List["Node"]:
        return [it for it in self.items if isinstance(it, Node)]

    def find(self, head: str) -> Iterator["Node"]:
        """Sublistas directas con ese nombre."""
        for child in self.lists():
            if child.head == head:
                yield child

    def find_deep(self, head: str) -> Iterator["Node"]:
        """Igual, pero a cualquier profundidad."""
        for child in self.lists():
            if child.head == head:
                yield child
            yield from child.find_deep(head)

    def __repr__(self) -> str:  # pragma: no cover - solo para depurar
        return f"Node({self.head!r}, {len(self.items)} items)"


Element = Union[Atom, Node]
Token = Tuple[str, int, str]


class ParseError(ValueError):
    """El fichero no es una s-expression valida."""


def tokenize(text: str) -> Iterator[Token]:
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char in _WHITESPACE:
            i += 1
        elif char in "()":
            yield (char, i, char)
            i += 1
        elif char == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            if j >= n:
                raise ParseError(f"cadena sin cerrar en la posicion {i}")
            yield ("str", i, "".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in _ATOM_END:
                j += 1
            yield ("sym", i, text[i:j])
            i = j


def parse(text: str) -> Node:
    """Devuelve el nodo raiz del documento."""
    tokens = list(tokenize(text))
    pos = 0

    while pos < len(tokens) and tokens[pos][0] != "(":
        pos += 1
    if pos >= len(tokens):
        raise ParseError("no se encontro ninguna s-expression")

    stack: List[Tuple[int, List[Element]]] = []
    root: Optional[Node] = None

    for kind, offset, value in tokens[pos:]:
        if kind == "(":
            stack.append((offset, []))
        elif kind == ")":
            if not stack:
                raise ParseError(f"parentesis de cierre sobrante en {offset}")
            start, items = stack.pop()
            node = Node(items, start, offset + 1)
            if stack:
                stack[-1][1].append(node)
            else:
                root = node
                break
        else:
            if not stack:
                raise ParseError(f"atomo fuera de toda lista en {offset}")
            stack[-1][1].append(Atom(value, kind == "str", offset))

    if root is None:
        raise ParseError("parentesis sin cerrar")
    return root
