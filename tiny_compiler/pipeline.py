"""High-level API that chains all compiler phases."""
from __future__ import annotations

from typing import Iterable, List, Optional

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


def compile_source(source: str) -> CompilationResult:
    """Run lexer -> parser -> semantic analysis -> IR -> code generation.

    The pipeline stops after the first phase that reports errors, so that
    later phases never see malformed input.
    """
    res = CompilationResult(source)
    diags = res.diagnostics
    res.tokens = tokenize(source, diags)
    if diags.has_errors():
        return res
    res.ast = parse(res.tokens, diags)
    if diags.has_errors():
        return res
    res.symbols = analyze(res.ast, diags)
    if diags.has_errors():
        return res
    res.ir = generate_ir(res.ast)
    res.code = generate_code(res.ir)
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
