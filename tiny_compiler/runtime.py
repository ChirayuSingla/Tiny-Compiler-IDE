"""Run-time support shared by the TAC interpreter and the stack VM.

Keeping the arithmetic and I/O rules in one place guarantees both back-ends
implement identical semantics.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, TextIO

from .diagnostics import TinyRuntimeError

_INT_RE = re.compile(r"^[+-]?[0-9]+$")


def int_div(a: int, b: int) -> int:
    """Integer division truncating toward zero (C semantics)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def int_mod(a: int, b: int) -> int:
    """Remainder with the sign of the dividend, so a == (a/b)*b + a%b."""
    return a - b * int_div(a, b)


def apply_binary(op: str, a, b, line: int = 0):
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise TinyRuntimeError("division by zero", line)
        return int_div(a, b)
    if op == "%":
        if b == 0:
            raise TinyRuntimeError("modulo by zero", line)
        return int_mod(a, b)
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    raise ValueError("unknown binary operator %r" % op)


def apply_unary(op: str, a):
    if op == "neg":
        return -a
    if op == "not":
        return not a
    raise ValueError("unknown unary operator %r" % op)


def format_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


class InputReader:
    """Supplies whitespace-separated tokens to `read` statements.

    `source` is either an iterable of lines (a text stream) or None for
    "no input".  When `prompt_stream` is given (interactive terminals) a
    prompt is printed before waiting for each token.
    """

    def __init__(self, source: Optional[Iterable[str]] = None,
                 prompt_stream: Optional[TextIO] = None) -> None:
        self._lines = iter(source) if source is not None else iter(())
        self._pending: List[str] = []
        self._prompt_stream = prompt_stream

    @classmethod
    def from_text(cls, text: str) -> "InputReader":
        return cls(text.splitlines())

    def _next_token(self, name: str) -> Optional[str]:
        while not self._pending:
            if self._prompt_stream is not None:
                self._prompt_stream.write("read %s> " % name)
                self._prompt_stream.flush()
            try:
                line = next(self._lines)
            except StopIteration:
                return None
            # Windows PowerShell prepends a UTF-8 byte-order mark when piping text.
            self._pending = line.lstrip("﻿").split()
        return self._pending.pop(0)

    def read_value(self, type_name: str, name: str, line: int = 0):
        tok = self._next_token(name)
        if tok is None:
            raise TinyRuntimeError("no more input available for 'read %s'" % name, line)
        if type_name == "bool":
            low = tok.lower()
            if low == "true":
                return True
            if low == "false":
                return False
            raise TinyRuntimeError("invalid bool input %r for '%s' (expected true or false)"
                                   % (tok, name), line)
        if not _INT_RE.match(tok):
            raise TinyRuntimeError("invalid integer input %r for '%s'" % (tok, name), line)
        return int(tok)


class OutputWriter:
    """Collects or forwards program output."""

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self._stream = stream
        self._parts: List[str] = []

    def write(self, text: str) -> None:
        if self._stream is not None:
            self._stream.write(text)
        else:
            self._parts.append(text)

    def getvalue(self) -> str:
        return "".join(self._parts)


DEFAULT_MAX_STEPS = 5000000


def too_many_steps(limit: int, line: int) -> TinyRuntimeError:
    return TinyRuntimeError("execution stopped after %d steps (possible infinite loop; "
                            "raise the limit with --max-steps)" % limit, line)
