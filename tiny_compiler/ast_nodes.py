"""AST node definitions and a text pretty-printer.

Semantic analysis annotates nodes in place: expression nodes receive `type`
("int" / "bool" / "string" / "error") and variable-bearing nodes receive `symbol`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

TYPE_INT = "int"
TYPE_BOOL = "bool"
TYPE_STRING = "string"
TYPE_ERROR = "error"  # produced after a reported error, suppresses cascades


class Node:
    line = 0
    col = 0


# ---- expressions ---------------------------------------------------------
@dataclass
class IntLit(Node):
    value: int
    line: int = 0
    col: int = 0
    type: Optional[str] = field(default=None, compare=False)


@dataclass
class BoolLit(Node):
    value: bool
    line: int = 0
    col: int = 0
    type: Optional[str] = field(default=None, compare=False)


@dataclass
class StringLit(Node):
    value: str
    line: int = 0
    col: int = 0
    type: Optional[str] = field(default=None, compare=False)


@dataclass
class VarRef(Node):
    name: str
    line: int = 0
    col: int = 0
    type: Optional[str] = field(default=None, compare=False)
    symbol: Any = field(default=None, compare=False, repr=False)


@dataclass
class Unary(Node):
    op: str  # "-" or "not"
    operand: Any
    line: int = 0
    col: int = 0
    type: Optional[str] = field(default=None, compare=False)


@dataclass
class Binary(Node):
    op: str
    left: Any
    right: Any
    line: int = 0
    col: int = 0
    type: Optional[str] = field(default=None, compare=False)


# ---- statements ----------------------------------------------------------
@dataclass
class VarDecl(Node):
    name: str
    type_name: str
    init: Optional[Any] = None
    line: int = 0
    col: int = 0
    symbol: Any = field(default=None, compare=False, repr=False)


@dataclass
class Assign(Node):
    name: str
    value: Any
    line: int = 0
    col: int = 0
    symbol: Any = field(default=None, compare=False, repr=False)


@dataclass
class Block(Node):
    statements: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class If(Node):
    cond: Any
    then_block: Block
    else_branch: Optional[Any] = None  # Block, If (else-if chain) or None
    line: int = 0
    col: int = 0


@dataclass
class While(Node):
    cond: Any
    body: Block
    line: int = 0
    col: int = 0


@dataclass
class Read(Node):
    name: str
    line: int = 0
    col: int = 0
    symbol: Any = field(default=None, compare=False, repr=False)


@dataclass
class Write(Node):
    items: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class Program(Node):
    statements: List[Any]
    line: int = 1
    col: int = 1


# ---- pretty printer --------------------------------------------------------
def _type_suffix(node) -> str:
    t = getattr(node, "type", None)
    return " : %s" % t if t else ""


def _label(node) -> str:
    if isinstance(node, IntLit):
        return "IntLit %d%s" % (node.value, _type_suffix(node))
    if isinstance(node, BoolLit):
        return "BoolLit %s%s" % ("true" if node.value else "false", _type_suffix(node))
    if isinstance(node, StringLit):
        return "StringLit %r%s" % (node.value, _type_suffix(node))
    if isinstance(node, VarRef):
        return "VarRef %s%s" % (node.name, _type_suffix(node))
    if isinstance(node, Unary):
        return "Unary '%s'%s" % (node.op, _type_suffix(node))
    if isinstance(node, Binary):
        return "Binary '%s'%s" % (node.op, _type_suffix(node))
    if isinstance(node, VarDecl):
        return "VarDecl %s : %s" % (node.name, node.type_name)
    if isinstance(node, Assign):
        return "Assign %s" % node.name
    if isinstance(node, Read):
        return "Read %s" % node.name
    return type(node).__name__


def _children(node):
    if isinstance(node, Program) or isinstance(node, Block):
        return list(node.statements)
    if isinstance(node, VarDecl):
        return [node.init] if node.init is not None else []
    if isinstance(node, Assign):
        return [node.value]
    if isinstance(node, If):
        kids = [node.cond, node.then_block]
        if node.else_branch is not None:
            kids.append(node.else_branch)
        return kids
    if isinstance(node, While):
        return [node.cond, node.body]
    if isinstance(node, Write):
        return list(node.items)
    if isinstance(node, Unary):
        return [node.operand]
    if isinstance(node, Binary):
        return [node.left, node.right]
    return []


def format_ast(node) -> str:
    """Render the AST as an indented tree."""
    out: List[str] = []

    def walk(n, prefix: str, is_last: bool, is_root: bool) -> None:
        if is_root:
            out.append(_label(n))
            child_prefix = ""
        else:
            out.append(prefix + ("`-- " if is_last else "|-- ") + _label(n))
            child_prefix = prefix + ("    " if is_last else "|   ")
        kids = _children(n)
        for i, k in enumerate(kids):
            walk(k, child_prefix, i == len(kids) - 1, False)

    walk(node, "", True, True)
    return "\n".join(out)
