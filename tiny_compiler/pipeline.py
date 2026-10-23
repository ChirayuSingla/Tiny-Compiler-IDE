"""High-level API that chains all compiler phases."""
from __future__ import annotations

from typing import Callable, Iterable, List, Optional

from . import ast_nodes as A
from .codegen import VMInstr, generate_code
from .diagnostics import CompileError, DiagnosticBag
from .ir import Instr, generate_ir, interpret_tac
from .lexer import Token, tokenize
from .parser import parse
from .runtime import DEFAULT_MAX_STEPS, InputReader, OutputWriter
from .semantic import analyze
from .symbol_table import SymbolTable
from .vm import VM


class CompilationResult:
    """Everything produced so far; later fields stay None if an earlier phase failed."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.diagnostics = DiagnosticBag()
        self.tokens: Optional[List[Token]] = None
        self.ast: Optional[A.Program] = None
        self.symbols: Optional[SymbolTable] = None
        self.ir: Optional[List[Instr]] = None
        self.code: Optional[List[VMInstr]] = None

    @property
    def ok(self) -> bool:
        return self.code is not None and not self.diagnostics.has_errors()


def compile_source(source: str, on_stage: Optional[Callable] = None) -> CompilationResult:
    """Run lexer -> parser -> semantic analysis -> IR -> code generation.

    The pipeline stops after the first phase that reports errors, so that
    later phases never see malformed input.
    """
    res = CompilationResult(source)
    diags = res.diagnostics
    # Observers receive this run's real partial result; callers retaining an
    # event across threads must copy it because semantic analysis annotates ASTs.
    def notify(stage, status):
        if on_stage is not None:
            on_stage(stage, status, res)

    notify("source", "completed")
    phases = [
        ("lexical", "tokens", lambda: tokenize(source, diags)),
        ("syntax", "ast", lambda: parse(res.tokens, diags)),
        ("semantic", "symbols", lambda: analyze(res.ast, diags)),
        ("ir", "ir", lambda: generate_ir(res.ast)),
        ("code", "code", lambda: generate_code(res.ir)),
    ]
    for stage, field, action in phases:
        notify(stage, "active")
        try:
            setattr(res, field, action())
        except Exception:
            notify(stage, "error")
            raise
        failed = diags.has_errors()
        notify(stage, "error" if failed else "completed")
        if stage == "semantic":
            notify("symbols", "partial" if failed else "completed")
        if failed:
            break
    return res


def compile_or_raise(source: str, filename: str = "<input>") -> CompilationResult:
    res = compile_source(source)
    if not res.ok:
        raise CompileError(res.diagnostics.sorted(), source, filename)
    return res


def run_source(source: str, inputs: Optional[Iterable[str]] = None, backend: str = "vm",
               max_steps: int = DEFAULT_MAX_STEPS, filename: str = "<input>") -> str:
    """Compile and execute `source`; returns everything the program wrote.

    `inputs` is an iterable of input lines.  `backend` is "vm" (stack
    machine) or "ir" (three-address-code interpreter).
    """
    res = compile_or_raise(source, filename)
    reader = InputReader(inputs)
    if backend == "vm":
        return VM(res.code, reader, max_steps=max_steps).run().getvalue()
    if backend == "ir":
        return interpret_tac(res.ir, reader, max_steps=max_steps).getvalue()
    raise ValueError("unknown backend %r" % backend)
