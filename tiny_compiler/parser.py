"""Recursive-descent parser: tokens -> AST (see docs/GRAMMAR.md).

Syntax errors are recorded in a DiagnosticBag; the parser then re-synchronises
at the next statement boundary so that several errors can be reported at once.
"""
from __future__ import annotations

from typing import List, Optional

from . import ast_nodes as A
from .diagnostics import SYNTAX, DiagnosticBag
from .lexer import EOF, IDENT, INT, STRING, Token

# Words that are common in other languages but are not part of Tiny.  They are
# lexed as ordinary identifiers; the parser rejects them with a helpful message.
UNSUPPORTED = {
    "for": "'for' loops are not supported in Tiny; use 'while'",
    "do": "'do-while' loops are not supported in Tiny; use 'while'",
    "elif": "'elif' is not supported; write 'else { if (...) { ... } }' or 'else if (...) { ... }'",
    "elsif": "'elsif' is not supported; write 'else if (...) { ... }'",
    "function": "functions are not supported in Tiny",
    "func": "functions are not supported in Tiny",
    "def": "functions are not supported in Tiny",
    "return": "'return' is not supported in Tiny (there are no functions)",
    "break": "'break' is not supported in Tiny",
    "continue": "'continue' is not supported in Tiny",
    "switch": "'switch' is not supported in Tiny; use 'if' / 'else'",
    "print": "'print' is not a Tiny statement; use 'write'",
    "println": "'println' is not a Tiny statement; use 'write'",
    "input": "'input' is not a Tiny statement; use 'read'",
    "let": "'let' is not a Tiny keyword; declare variables with 'var name: int;'",
    "float": "floating-point types are not supported; Tiny has only 'int' and 'bool'",
    "double": "floating-point types are not supported; Tiny has only 'int' and 'bool'",
    "string": "string variables are not supported; strings may only appear in 'write'",
    "char": "'char' is not supported in Tiny",
}

TYPE_KEYWORDS = ("int", "bool")
COMPARISON_OPS = ("==", "!=", "<", "<=", ">", ">=")


class _SyntaxAbort(Exception):
    """Internal: unwinds to the statement loop after an error was recorded."""


class Parser:
    def __init__(self, tokens: List[Token], diagnostics: Optional[DiagnosticBag] = None) -> None:
        self.tokens = tokens
        self.diags = diagnostics if diagnostics is not None else DiagnosticBag()
        self.pos = 0
        # Set when a statement is merely missing its ';' - the current token
        # then probably starts the next statement and must not be skipped.
        self._resume_here = False

    # -- token helpers -----------------------------------------------------
    @property
    def tok(self) -> Token:
        return self.tokens[self.pos]

    def _prev(self) -> Token:
        return self.tokens[self.pos - 1] if self.pos > 0 else self.tokens[0]

    def _at(self, *types: str) -> bool:
        return self.tok.type in types

    def _advance(self) -> Token:
        t = self.tok
        if t.type != EOF:
            self.pos += 1
        return t

    def _describe(self, t: Token) -> str:
        if t.type == EOF:
            return "end of file"
        if t.type == IDENT:
            return "identifier '%s'" % t.lexeme
        if t.type == INT:
            return "number '%s'" % t.lexeme
        if t.type == STRING:
            return "string %s" % t.lexeme
        return "'%s'" % t.lexeme

    def _fail(self, message: str, tok: Optional[Token] = None, after_prev: bool = False):
        if after_prev and self.pos > 0:
            p = self._prev()
            line, col = p.line, p.end_col
        else:
            t = tok if tok is not None else self.tok
            line, col = t.line, t.col
        self.diags.error(SYNTAX, message, line, col)
        raise _SyntaxAbort()

    def _expect(self, ttype: str, context: str, after_prev: bool = False) -> Token:
        if self.tok.type == ttype:
            return self._advance()
        if ttype == ";" and after_prev and self.tok.type in (IDENT, "var", "if", "while",
                                                              "read", "write", "}"):
            self._resume_here = True
        self._fail("expected '%s' %s, found %s" % (ttype, context, self._describe(self.tok)),
                   after_prev=after_prev)

    def _expect_ident(self, context: str) -> Token:
        if self.tok.type == IDENT:
            return self._advance()
        self._fail("expected a variable name %s, found %s" % (context, self._describe(self.tok)))

    # -- program / statements ------------------------------------------------
    def parse(self) -> A.Program:
        stmts = self._statement_list(top_level=True)
        return A.Program(stmts, 1, 1)

    def _statement_list(self, top_level: bool) -> List[A.Node]:
        stmts: List[A.Node] = []
        while not self._at(EOF):
            if not top_level and self._at("}"):
                break
            start = self.pos
            try:
                stmts.append(self._statement())
            except _SyntaxAbort:
                self._synchronize()
                if self.pos == start:
                    self._advance()  # guarantee progress
        return stmts

    def _synchronize(self) -> None:
        """Skip to just after the next ';' or to a '}' / statement keyword."""
        starters = ("var", "if", "while", "read", "write", "{", "}")
        if self._resume_here:
            self._resume_here = False
            return
        while not self._at(EOF):
            if self._prev().type == ";" and self.pos > 0:
                return
            if self.tok.type in starters:
                return
            self._advance()

    def _statement(self) -> A.Node:
        t = self.tok
        if t.type == "var":
            return self._var_decl()
        if t.type == IDENT:
            if t.lexeme in UNSUPPORTED and self._next_type() != "=":
                self._fail(UNSUPPORTED[t.lexeme])
            return self._assignment()
        if t.type == "if":
            return self._if()
        if t.type == "while":
            return self._while()
        if t.type == "read":
            return self._read()
        if t.type == "write":
            return self._write()
        if t.type == "{":
            return self._block()
        if t.type == "}":
            self._fail("unexpected '}' with no matching '{'")
        if t.type == "else":
            self._fail("'else' without a matching 'if'")
        self._fail("expected a statement, found %s" % self._describe(t))

    def _next_type(self) -> str:
        i = self.pos + 1
        return self.tokens[i].type if i < len(self.tokens) else EOF

    def _var_decl(self) -> A.VarDecl:
        kw = self._advance()  # 'var'
        name = self._expect_ident("after 'var'")
        self._expect(":", "after the variable name (e.g. 'var x: int;')")
        if self._at(*TYPE_KEYWORDS):
            tname = self._advance().type
        elif self.tok.type == IDENT and self.tok.lexeme in UNSUPPORTED:
            self._fail("unknown type '%s': %s" % (self.tok.lexeme, UNSUPPORTED[self.tok.lexeme]))
        else:
            self._fail("expected a type ('int' or 'bool'), found %s" % self._describe(self.tok))
        init = None
        if self._at("="):
            self._advance()
            init = self._expression()
        self._expect(";", "at the end of the declaration", after_prev=True)
        return A.VarDecl(name.lexeme, tname, init, name.line, name.col)

    def _assignment(self) -> A.Assign:
        name = self._advance()
        if not self._at("="):
            self._fail("expected '=' after '%s' (assignment) but found %s"
                       % (name.lexeme, self._describe(self.tok)))
        self._advance()
        value = self._expression()
        self._expect(";", "at the end of the assignment", after_prev=True)
        return A.Assign(name.lexeme, value, name.line, name.col)

    def _block(self) -> A.Block:
        lb = self._expect("{", "to start a block")
        stmts = self._statement_list(top_level=False)
        if not self._at("}"):
            self.diags.error(SYNTAX, "expected '}' to close the block opened at line %d:%d"
                             % (lb.line, lb.col), self.tok.line, self.tok.col)
            raise _SyntaxAbort()
        self._advance()
        return A.Block(stmts, lb.line, lb.col)

    def _require_block(self, what: str) -> A.Block:
        if not self._at("{"):
            self._fail("expected '{' to start the body of %s, found %s "
                       "(Tiny requires braces around bodies)" % (what, self._describe(self.tok)))
        return self._block()

    def _paren_condition(self, keyword: str) -> A.Node:
        self._expect("(", "after '%s'" % keyword)
        cond = self._expression()
        self._expect(")", "after the condition")
        return cond

    def _if(self) -> A.If:
        kw = self._advance()
        cond = self._paren_condition("if")
        then_block = self._require_block("'if'")
        else_branch = None
        if self._at("else"):
            self._advance()
            if self._at("if"):
                else_branch = self._if()
            else:
                else_branch = self._require_block("'else'")
        return A.If(cond, then_block, else_branch, kw.line, kw.col)

    def _while(self) -> A.While:
        kw = self._advance()
        cond = self._paren_condition("while")
        body = self._require_block("'while'")
        return A.While(cond, body, kw.line, kw.col)

    def _read(self) -> A.Read:
        kw = self._advance()
        name = self._expect_ident("after 'read'")
        self._expect(";", "after the variable in 'read'", after_prev=True)
        return A.Read(name.lexeme, name.line, name.col)

    def _write(self) -> A.Write:
        kw = self._advance()
        items = [self._write_item()]
        while self._at(","):
            self._advance()
            items.append(self._write_item())
        self._expect(";", "at the end of the 'write' statement", after_prev=True)
        return A.Write(items, kw.line, kw.col)

    def _write_item(self) -> A.Node:
        if self._at(STRING):
            t = self._advance()
            return A.StringLit(t.value, t.line, t.col)
        return self._expression()

    # -- expressions (lowest to highest precedence) ----------------------------
    def _expression(self) -> A.Node:
        return self._or()

    def _or(self) -> A.Node:
        left = self._and()
        while self._at("or"):
            op = self._advance()
            right = self._and()
            left = A.Binary("or", left, right, op.line, op.col)
        return left

    def _and(self) -> A.Node:
        left = self._not()
        while self._at("and"):
            op = self._advance()
            right = self._not()
            left = A.Binary("and", left, right, op.line, op.col)
        return left

    def _not(self) -> A.Node:
        if self._at("not"):
            op = self._advance()
            return A.Unary("not", self._not(), op.line, op.col)
        return self._comparison()

    def _comparison(self) -> A.Node:
        left = self._additive()
        if self._at(*COMPARISON_OPS):
            op = self._advance()
            right = self._additive()
            if self._at(*COMPARISON_OPS):
                self._fail("comparison operators cannot be chained; "
                           "combine comparisons with 'and' / 'or'")
            return A.Binary(op.type, left, right, op.line, op.col)
        return left

    def _additive(self) -> A.Node:
        left = self._term()
        while self._at("+", "-"):
            op = self._advance()
            right = self._term()
            left = A.Binary(op.type, left, right, op.line, op.col)
        return left

    def _term(self) -> A.Node:
        left = self._unary()
        while self._at("*", "/", "%"):
            op = self._advance()
            right = self._unary()
            left = A.Binary(op.type, left, right, op.line, op.col)
        return left

    def _unary(self) -> A.Node:
        if self._at("-"):
            op = self._advance()
            return A.Unary("-", self._unary(), op.line, op.col)
        return self._primary()

    def _primary(self) -> A.Node:
        t = self.tok
        if t.type == INT:
            self._advance()
            return A.IntLit(t.value, t.line, t.col)
        if t.type == "true" or t.type == "false":
            self._advance()
            return A.BoolLit(t.type == "true", t.line, t.col)
        if t.type == IDENT:
            if t.lexeme in UNSUPPORTED and self._next_type() == "(":
                self._fail(UNSUPPORTED[t.lexeme])
            self._advance()
            if self._at("("):
                self._fail("function calls are not supported in Tiny", tok=t)
            return A.VarRef(t.lexeme, t.line, t.col)
        if t.type == "(":
            self._advance()
            inner = self._expression()
            self._expect(")", "to close the parenthesised expression")
            return inner
        if t.type == STRING:
            self._fail("string literals may only appear directly in a 'write' statement")
        if t.type == EOF or t.type in (";", ")", "}", ","):
            self._fail("expected an expression, found %s" % self._describe(t),
                       after_prev=(t.type == ";" or t.type == EOF))
        self._fail("expected an expression, found %s" % self._describe(t))


def parse(tokens: List[Token], diagnostics: Optional[DiagnosticBag] = None) -> A.Program:
    return Parser(tokens, diagnostics).parse()
