"""Semantic analysis: declarations, scopes and type checking.

Type rules (see docs/LANGUAGE_SPEC.md):
  * arithmetic  + - * / %  and unary -      : int x int -> int
  * ordering    < <= > >=                   : int x int -> bool
  * equality    == !=                       : T x T -> bool   (T = int or bool)
  * logic       and or not                  : bool -> bool
  * conditions of 'if' / 'while'            : bool
  * assignment / initialiser                : value type must equal variable type
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import ast_nodes as A
from .diagnostics import SEMANTIC, DiagnosticBag
from .symbol_table import SymbolTable

ARITH = ("+", "-", "*", "/", "%")
ORDER = ("<", "<=", ">", ">=")
EQUAL = ("==", "!=")


def eval_const(node) -> Optional[int]:
    """Evaluate an integer expression made only of literals, else None.

    Used to detect division by a constant zero at compile time.
    """
    if isinstance(node, A.IntLit):
        return node.value
    if isinstance(node, A.Unary) and node.op == "-":
        v = eval_const(node.operand)
        return -v if v is not None else None
    if isinstance(node, A.Binary) and node.op in ARITH:
        a = eval_const(node.left)
        b = eval_const(node.right)
        if a is None or b is None:
            return None
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if b == 0:
            return None
        from .runtime import int_div, int_mod
        return int_div(a, b) if node.op == "/" else int_mod(a, b)
    return None


class SemanticAnalyzer:
    def __init__(self, diagnostics: Optional[DiagnosticBag] = None) -> None:
        self.diags = diagnostics if diagnostics is not None else DiagnosticBag()
        self.table = SymbolTable()

    def analyze(self, program: A.Program) -> SymbolTable:
        self._block_body(program.statements)
        for sym in self.table.all_symbols:
            if not sym.used and not self.diags.has_errors():
                self.diags.warning(SEMANTIC, "variable '%s' is declared but its value is "
                                   "never read" % sym.name, sym.line, sym.col)
        return self.table

    # -- statements ----------------------------------------------------------
    def _block_body(self, statements: List[A.Node]) -> None:
        scope = self.table.current
        for st in statements:
            if isinstance(st, A.VarDecl) and st.name not in scope.pending:
                scope.pending[st.name] = st.line
        for st in statements:
            self._stmt(st)

    def _error(self, message: str, node) -> None:
        self.diags.error(SEMANTIC, message, node.line, node.col)

    def _stmt(self, st) -> None:
        if isinstance(st, A.VarDecl):
            self._var_decl(st)
        elif isinstance(st, A.Assign):
            self._assign(st)
        elif isinstance(st, A.Block):
            self._scoped_block(st)
        elif isinstance(st, A.If):
            self._condition(st.cond, "if")
            self._scoped_block(st.then_block)
            if st.else_branch is not None:
                if isinstance(st.else_branch, A.If):
                    self._stmt(st.else_branch)
                else:
                    self._scoped_block(st.else_branch)
        elif isinstance(st, A.While):
            self._condition(st.cond, "while")
            self._scoped_block(st.body)
        elif isinstance(st, A.Read):
            sym = self._resolve(st.name, st)
            st.symbol = sym
        elif isinstance(st, A.Write):
            for item in st.items:
                if isinstance(item, A.StringLit):
                    item.type = A.TYPE_STRING
                else:
                    self._expr(item)
        else:  # pragma: no cover - parser never produces anything else
            raise AssertionError("unknown statement node %r" % (st,))

    def _scoped_block(self, block: A.Block) -> None:
        self.table.enter_scope()
        self._block_body(block.statements)
        self.table.exit_scope()

    def _var_decl(self, st: A.VarDecl) -> None:
        # The initialiser is analysed before the name is declared, so
        # `var x: int = x;` refers to an *outer* x or is an error.
        init_type = None
        if st.init is not None:
            init_type = self._expr(st.init)
        scope = self.table.current
        scope.pending.pop(st.name, None)
        sym = self.table.declare(st.name, st.type_name, st.line, st.col)
        if sym is None:
            prev = self.table.lookup_current(st.name)
            self._error("variable '%s' is already declared in this scope (first declared at "
                        "line %d:%d)" % (st.name, prev.line, prev.col), st)
            st.symbol = prev
            return
        st.symbol = sym
        if init_type is not None and init_type != A.TYPE_ERROR and init_type != st.type_name:
            self._error("cannot initialise '%s' variable '%s' with a value of type '%s'"
                        % (st.type_name, st.name, init_type), st.init)

    def _assign(self, st: A.Assign) -> None:
        sym = self._resolve(st.name, st)
        st.symbol = sym
        vtype = self._expr(st.value)
        if sym is None or vtype == A.TYPE_ERROR:
            return
        if vtype != sym.type:
            self._error("cannot assign a value of type '%s' to '%s' variable '%s'"
                        % (vtype, sym.type, st.name), st)

    def _condition(self, cond, keyword: str) -> None:
        t = self._expr(cond)
        if t != A.TYPE_ERROR and t != A.TYPE_BOOL:
            self._error("the condition of '%s' must be of type 'bool', not '%s' "
                        "(hint: compare with a relational operator, e.g. 'x != 0')"
                        % (keyword, t), cond)

    # -- names ---------------------------------------------------------------
    def _resolve(self, name: str, node):
        # Walk outwards; a name that is still *pending* in a nearer block hides
        # any outer variable of the same name, so using it early is an error.
        scope = self.table.current
        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            if name in scope.pending:
                self._error("variable '%s' is used before its declaration (it is declared "
                            "later, at line %d)" % (name, scope.pending[name]), node)
                return None
            scope = scope.parent
        self._error("variable '%s' is not declared (declare it with 'var %s: int;')"
                    % (name, name), node)
        return None

    # -- expressions ---------------------------------------------------------
    def _expr(self, e) -> str:
        t = self._expr_inner(e)
        e.type = t
        return t

    def _expr_inner(self, e) -> str:
        if isinstance(e, A.IntLit):
            return A.TYPE_INT
        if isinstance(e, A.BoolLit):
            return A.TYPE_BOOL
        if isinstance(e, A.StringLit):
            self._error("string literals may only appear directly in a 'write' statement", e)
            return A.TYPE_ERROR
        if isinstance(e, A.VarRef):
            sym = self._resolve(e.name, e)
            e.symbol = sym
            if sym is None:
                return A.TYPE_ERROR
            sym.used = True
            return sym.type
        if isinstance(e, A.Unary):
            ot = self._expr(e.operand)
            if ot == A.TYPE_ERROR:
                return A.TYPE_ERROR
            if e.op == "-":
                if ot != A.TYPE_INT:
                    self._error("unary '-' needs an 'int' operand, not '%s'" % ot, e)
                    return A.TYPE_ERROR
                return A.TYPE_INT
            if ot != A.TYPE_BOOL:
                self._error("'not' needs a 'bool' operand, not '%s'" % ot, e)
                return A.TYPE_ERROR
            return A.TYPE_BOOL
        if isinstance(e, A.Binary):
            return self._binary(e)
        raise AssertionError("unknown expression node %r" % (e,))  # pragma: no cover

    def _binary(self, e: A.Binary) -> str:
        lt = self._expr(e.left)
        rt = self._expr(e.right)
        if lt == A.TYPE_ERROR or rt == A.TYPE_ERROR:
            return A.TYPE_ERROR
        op = e.op
        if op in ARITH:
            if lt != A.TYPE_INT or rt != A.TYPE_INT:
                self._error("operator '%s' needs two 'int' operands, but got '%s' and '%s'"
                            % (op, lt, rt), e)
                return A.TYPE_ERROR
            if op in ("/", "%") and eval_const(e.right) == 0:
                self._error("division by zero: the divisor of '%s' is always 0" % op, e)
                return A.TYPE_ERROR
            return A.TYPE_INT
        if op in ORDER:
            if lt != A.TYPE_INT or rt != A.TYPE_INT:
                self._error("operator '%s' needs two 'int' operands, but got '%s' and '%s'"
                            % (op, lt, rt), e)
                return A.TYPE_ERROR
            return A.TYPE_BOOL
        if op in EQUAL:
            if lt != rt:
                self._error("cannot compare '%s' with '%s' using '%s'; both sides must have "
                            "the same type" % (lt, rt, op), e)
                return A.TYPE_ERROR
            return A.TYPE_BOOL
        if op in ("and", "or"):
            if lt != A.TYPE_BOOL or rt != A.TYPE_BOOL:
                self._error("operator '%s' needs two 'bool' operands, but got '%s' and '%s'"
                            % (op, lt, rt), e)
                return A.TYPE_ERROR
            return A.TYPE_BOOL
        raise AssertionError("unknown operator %r" % op)  # pragma: no cover


def analyze(program: A.Program, diagnostics: Optional[DiagnosticBag] = None) -> SymbolTable:
    return SemanticAnalyzer(diagnostics).analyze(program)
