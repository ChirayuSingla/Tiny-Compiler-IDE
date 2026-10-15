"""Diagnostics: error/warning records, source-position rendering, exceptions."""
from __future__ import annotations

from typing import List, Optional

LEXICAL = "lexical"
SYNTAX = "syntax"
SEMANTIC = "semantic"
RUNTIME = "runtime"

ERROR = "error"
WARNING = "warning"


class Diagnostic:
    """One message about the source program, with a 1-based line/column."""

    def __init__(self, phase: str, message: str, line: int, col: int,
                 severity: str = ERROR) -> None:
        self.phase = phase
        self.message = message
        self.line = line
        self.col = col
        self.severity = severity

    def __repr__(self) -> str:
        return "Diagnostic(%s, %r, %d:%d)" % (self.phase, self.message, self.line, self.col)

    def label(self) -> str:
        if self.severity == WARNING:
            return "warning"
        return "%s error" % self.phase

    def format(self, source: Optional[str] = None, filename: str = "<input>") -> str:
        head = "%s:%d:%d: %s: %s" % (filename, self.line, self.col, self.label(), self.message)
        if source is None or self.line < 1:
            return head
        lines = source.split("\n")
        if self.line > len(lines):
            return head
        text = lines[self.line - 1].rstrip("\r")
        gutter = "%5d | " % self.line
        pad = " " * (len(gutter) - 2) + "| "
        # Expand tabs the same way in the code line and the caret line.
        text = text.replace("\t", " ")
        caret = " " * max(self.col - 1, 0) + "^"
        return "%s\n%s%s\n%s%s" % (head, gutter, text, pad, caret)


class DiagnosticBag:
    """Collects diagnostics produced by one or more compiler phases."""

    def __init__(self) -> None:
        self.items: List[Diagnostic] = []

    def error(self, phase: str, message: str, line: int, col: int) -> None:
        self.items.append(Diagnostic(phase, message, line, col, ERROR))

    def warning(self, phase: str, message: str, line: int, col: int) -> None:
        self.items.append(Diagnostic(phase, message, line, col, WARNING))

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.items if d.severity == ERROR]

    @property
    def warnings(self) -> List[Diagnostic]:
        return [d for d in self.items if d.severity == WARNING]

    def has_errors(self) -> bool:
        return any(d.severity == ERROR for d in self.items)

    def sorted(self) -> List[Diagnostic]:
        return sorted(self.items, key=lambda d: (d.line, d.col))


def format_diagnostics(diags: List[Diagnostic], source: Optional[str],
                       filename: str = "<input>") -> str:
    return "\n".join(d.format(source, filename) for d in diags)


class CompileError(Exception):
    """Raised by the convenience API when compilation fails."""

    def __init__(self, diagnostics: List[Diagnostic], source: Optional[str] = None,
                 filename: str = "<input>") -> None:
        self.diagnostics = diagnostics
        self.source = source
        self.filename = filename
        super().__init__(format_diagnostics(diagnostics, source, filename))


class TinyRuntimeError(Exception):
    """A run-time failure (division by zero, bad input, step limit, ...)."""

    def __init__(self, message: str, line: int = 0) -> None:
        self.message = message
        self.line = line
        super().__init__(message)

    def format(self, filename: str = "<input>") -> str:
        if self.line:
            return "%s:%d: runtime error: %s" % (filename, self.line, self.message)
        return "%s: runtime error: %s" % (filename, self.message)
