"""Scoped symbol table used by semantic analysis."""
from __future__ import annotations

from typing import Dict, List, Optional


class Symbol:
    """A declared variable.

    `unique` is the storage name used by the IR and VM; a variable that
    shadows an outer one gets a distinct name such as ``x#1``.
    """

    def __init__(self, name: str, type_: str, unique: str, depth: int,
                 line: int, col: int) -> None:
        self.name = name
        self.type = type_
        self.unique = unique
        self.depth = depth
        self.line = line
        self.col = col
        self.used = False

    def __repr__(self) -> str:
        return "Symbol(%s:%s, %s, depth=%d)" % (self.name, self.type, self.unique, self.depth)


class Scope:
    def __init__(self, parent: Optional["Scope"], depth: int) -> None:
        self.parent = parent
        self.depth = depth
        self.symbols: Dict[str, Symbol] = {}
        # Names declared later in this same block; used to tell "used before
        # declaration" apart from "never declared".
        self.pending: Dict[str, int] = {}


class SymbolTable:
    def __init__(self) -> None:
        self.current = Scope(None, 0)
        self.all_symbols: List[Symbol] = []  # every symbol ever declared, in order
        self._name_counts: Dict[str, int] = {}

    @property
    def depth(self) -> int:
        return self.current.depth

    def enter_scope(self) -> Scope:
        self.current = Scope(self.current, self.current.depth + 1)
        return self.current

    def exit_scope(self) -> None:
        assert self.current.parent is not None
        self.current = self.current.parent

    def declare(self, name: str, type_: str, line: int, col: int) -> Optional[Symbol]:
        """Declare in the current scope; returns None if it is a duplicate."""
        if name in self.current.symbols:
            return None
        count = self._name_counts.get(name, 0)
        self._name_counts[name] = count + 1
        unique = name if count == 0 else "%s#%d" % (name, count)
        sym = Symbol(name, type_, unique, self.current.depth, line, col)
        self.current.symbols[name] = sym
        self.all_symbols.append(sym)
        return sym

    def lookup(self, name: str) -> Optional[Symbol]:
        scope: Optional[Scope] = self.current
        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        return None

    def lookup_current(self, name: str) -> Optional[Symbol]:
        return self.current.symbols.get(name)


def format_symbols(table: SymbolTable) -> str:
    rows = ["%-12s %-6s %-6s %-14s %-9s %s"
            % ("NAME", "TYPE", "SCOPE", "STORAGE", "DECLARED", "READ?")]
    for s in table.all_symbols:
        rows.append("%-12s %-6s %-6d %-14s %-9s %s"
                    % (s.name, s.type, s.depth, s.unique, "%d:%d" % (s.line, s.col),
                       "yes" if s.used else "no"))
    if not table.all_symbols:
        rows.append("(no variables declared)")
    return "\n".join(rows)
