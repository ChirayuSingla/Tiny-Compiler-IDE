"""Lexical analysis: source text -> list of tokens (with line/column)."""
from __future__ import annotations

from typing import List, Optional

from .diagnostics import LEXICAL, DiagnosticBag

KEYWORDS = frozenset([
    "var", "int", "bool", "if", "else", "while", "read", "write",
    "true", "false", "and", "or", "not",
])

# Two-character operators must be tried before one-character ones.
TWO_CHAR = ("==", "!=", "<=", ">=")
ONE_CHAR = "+-*/%<>=(){};:,"

# Token categories that are not simply the lexeme itself.
IDENT = "IDENT"
INT = "INT"
STRING = "STRING"
EOF = "EOF"

STRING_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


class Token:
    """A lexical token. For keywords and symbols `type` equals the lexeme."""

    __slots__ = ("type", "value", "lexeme", "line", "col")

    def __init__(self, type_: str, value, lexeme: str, line: int, col: int) -> None:
        self.type = type_
        self.value = value
        self.lexeme = lexeme
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return "Token(%s, %r, %d:%d)" % (self.type, self.lexeme, self.line, self.col)

    @property
    def end_col(self) -> int:
        return self.col + max(len(self.lexeme), 1)


def _is_ident_start(ch: str) -> bool:
    return ch == "_" or ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def _is_ident_part(ch: str) -> bool:
    return _is_ident_start(ch) or ("0" <= ch <= "9")


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


class Lexer:
    def __init__(self, source: str, diagnostics: Optional[DiagnosticBag] = None) -> None:
        self.src = source
        self.diags = diagnostics if diagnostics is not None else DiagnosticBag()
        self.pos = 0
        self.line = 1
        self.col = 1

    # -- helpers ---------------------------------------------------------
    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _error(self, message: str, line: int, col: int) -> None:
        self.diags.error(LEXICAL, message, line, col)

    # -- main entry ------------------------------------------------------
    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while True:
            self._skip_trivia()
            if self.pos >= len(self.src):
                tokens.append(Token(EOF, None, "", self.line, self.col))
                return tokens
            tok = self._next_token()
            if tok is not None:
                tokens.append(tok)

    def _skip_trivia(self) -> None:
        """Skip whitespace, // line comments and /* block comments */."""
        while self.pos < len(self.src):
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while self.pos < len(self.src) and self._peek() != "\n":
                    self._advance()
            elif ch == "/" and self._peek(1) == "*":
                line, col = self.line, self.col
                self._advance()
                self._advance()
                closed = False
                while self.pos < len(self.src):
                    if self._peek() == "*" and self._peek(1) == "/":
                        self._advance()
                        self._advance()
                        closed = True
                        break
                    self._advance()
                if not closed:
                    self._error("unterminated block comment (missing '*/')", line, col)
            else:
                return

    def _next_token(self) -> Optional[Token]:
        ch = self._peek()
        line, col = self.line, self.col

        if _is_ident_start(ch):
            start = self.pos
            while self.pos < len(self.src) and _is_ident_part(self._peek()):
                self._advance()
            text = self.src[start:self.pos]
            if text in KEYWORDS:
                return Token(text, text, text, line, col)
            return Token(IDENT, text, text, line, col)

        if _is_digit(ch):
            start = self.pos
            while self.pos < len(self.src) and _is_digit(self._peek()):
                self._advance()
            # A number glued to letters (e.g. 12abc) is malformed.
            if self.pos < len(self.src) and _is_ident_start(self._peek()):
                while self.pos < len(self.src) and _is_ident_part(self._peek()):
                    self._advance()
                text = self.src[start:self.pos]
                self._error("malformed number '%s' (identifiers cannot start with a digit)"
                            % text, line, col)
                return None
            text = self.src[start:self.pos]
            return Token(INT, int(text), text, line, col)

        if ch == '"':
            return self._string(line, col)

        two = ch + self._peek(1)
        if two in TWO_CHAR:
            self._advance()
            self._advance()
            return Token(two, two, two, line, col)

        if ch in ONE_CHAR:
            self._advance()
            return Token(ch, ch, ch, line, col)

        # Anything else is an invalid character; report it and keep scanning.
        self._advance()
        shown = ch if ch.isprintable() else "U+%04X" % ord(ch)
        if ch in "!&|":
            hint = {"!": " (did you mean '!=' or 'not'?)",
                    "&": " (use 'and' for logical and)",
                    "|": " (use 'or' for logical or)"}[ch]
        else:
            hint = ""
        self._error("invalid character '%s'%s" % (shown, hint), line, col)
        return None

    def _string(self, line: int, col: int) -> Optional[Token]:
        start = self.pos
        self._advance()  # opening quote
        chars: List[str] = []
        while True:
            if self.pos >= len(self.src) or self._peek() == "\n":
                self._error("unterminated string literal (missing closing '\"')", line, col)
                return None
            ch = self._advance()
            if ch == '"':
                break
            if ch == "\\":
                if self.pos >= len(self.src) or self._peek() == "\n":
                    self._error("unterminated string literal (missing closing '\"')", line, col)
                    return None
                esc_line, esc_col = self.line, self.col - 1
                esc = self._advance()
                if esc in STRING_ESCAPES:
                    chars.append(STRING_ESCAPES[esc])
                else:
                    self._error("unknown escape sequence '\\%s' in string" % esc,
                                esc_line, esc_col)
            else:
                chars.append(ch)
        lexeme = self.src[start:self.pos]
        return Token(STRING, "".join(chars), lexeme, line, col)


def tokenize(source: str, diagnostics: Optional[DiagnosticBag] = None) -> List[Token]:
    return Lexer(source, diagnostics).tokenize()


def format_tokens(tokens: List[Token]) -> str:
    rows = ["%-8s %-8s %s" % ("LOC", "TYPE", "LEXEME")]
    for t in tokens:
        loc = "%d:%d" % (t.line, t.col)
        if t.type == EOF:
            lexeme = "<end of file>"
        else:
            lexeme = t.lexeme.replace("\n", "\\n")
        rows.append("%-8s %-8s %s" % (loc, t.type, lexeme))
    return "\n".join(rows)
