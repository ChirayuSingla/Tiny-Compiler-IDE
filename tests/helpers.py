"""Shared helpers for the test-suite."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tiny_compiler import ast_nodes as A  # noqa: E402
from tiny_compiler.diagnostics import DiagnosticBag  # noqa: E402
from tiny_compiler.lexer import tokenize  # noqa: E402
from tiny_compiler.parser import parse  # noqa: E402
from tiny_compiler.pipeline import compile_source  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")


def parse_source(src):
    """Return (program, diagnostic bag) for the lexer+parser only."""
    bag = DiagnosticBag()
    toks = tokenize(src, bag)
    prog = parse(toks, bag)
    return prog, bag


def parse_ok(src):
    prog, bag = parse_source(src)
    assert not bag.has_errors(), [d.message for d in bag.errors]
    return prog


def sexpr(node):
    """Compact S-expression of an expression AST, for precedence tests."""
    if isinstance(node, A.IntLit):
        return str(node.value)
    if isinstance(node, A.BoolLit):
        return "true" if node.value else "false"
    if isinstance(node, A.VarRef):
        return node.name
    if isinstance(node, A.Unary):
        return "(%s %s)" % (node.op, sexpr(node.operand))
    if isinstance(node, A.Binary):
        return "(%s %s %s)" % (node.op, sexpr(node.left), sexpr(node.right))
    raise AssertionError(node)


def expr_of(src_expr):
    """Parse `x = <expr>;` and return the S-expression of the right-hand side."""
    prog = parse_ok("x = %s;" % src_expr)
    return sexpr(prog.statements[0].value)


def messages(bag):
    return [d.message for d in bag.errors]


def compile_errors(src):
    res = compile_source(src)
    return res, [d.message for d in res.diagnostics.errors]
