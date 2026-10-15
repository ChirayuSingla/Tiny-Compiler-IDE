"""Command-line interface.

Exit codes: 0 success, 1 compile error (lexical/syntax/semantic),
2 usage error (argparse), 3 run-time error, 4 file could not be read.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__
from .ast_nodes import format_ast
from .codegen import format_code
from .diagnostics import TinyRuntimeError, format_diagnostics
from .ir import format_ir, interpret_tac
from .lexer import format_tokens
from .pipeline import compile_source
from .runtime import DEFAULT_MAX_STEPS, InputReader, OutputWriter
from .symbol_table import format_symbols
from .vm import VM

EXIT_OK, EXIT_COMPILE, EXIT_RUNTIME, EXIT_IO = 0, 1, 3, 4


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tiny",
        description="Tiny Programming Language Compiler: source -> tokens -> AST -> "
                    "semantic check -> three-address code -> stack-VM code -> execution.")
    p.add_argument("file", help="path of a .tiny source file")
    p.add_argument("--tokens", action="store_true", help="show the token stream")
    p.add_argument("--ast", action="store_true", help="show the abstract syntax tree")
    p.add_argument("--symbols", action="store_true", help="show the symbol table")
    p.add_argument("--ir", action="store_true", help="show the three-address code")
    p.add_argument("--code", action="store_true", help="show the generated stack-machine code")
    p.add_argument("--all", action="store_true",
                   help="show every stage (tokens, AST, symbols, IR, code) and run")
    p.add_argument("--check", action="store_true",
                   help="compile only: report errors but do not run the program")
    p.add_argument("--backend", choices=("vm", "ir"), default="vm",
                   help="run the stack-VM code (default) or interpret the TAC directly")
    p.add_argument("--input", metavar="TEXT",
                   help="whitespace-separated values for 'read' statements "
                        "(otherwise they are read from standard input)")
    p.add_argument("--trace", action="store_true",
                   help="print every executed VM instruction with the stack (stderr)")
    p.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, metavar="N",
                   help="abort after N executed instructions (default %(default)s)")
    p.add_argument("--no-warnings", action="store_true", help="hide compiler warnings")
    p.add_argument("--version", action="version", version="tiny-compiler " + __version__)
    return p


def _section(title: str, body: str) -> None:
    print("=== %s ===" % title)
    print(body)
    print()


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            source = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        print("tiny: cannot read '%s': %s" % (args.file, exc), file=sys.stderr)
        return EXIT_IO

    res = compile_source(source)

    # Show whatever was produced before the first failing phase.
    show_tokens = args.tokens or args.all
    show_ast = args.ast or args.all
    show_syms = args.symbols or args.all
    show_ir = args.ir or args.all
    show_code = args.code or args.all
    any_stage = show_tokens or show_ast or show_syms or show_ir or show_code

    if show_tokens and res.tokens is not None:
        _section("Tokens", format_tokens(res.tokens))
    if show_ast and res.ast is not None and not res.diagnostics.has_errors():
        _section("AST", format_ast(res.ast))
    if show_syms and res.symbols is not None and not res.diagnostics.has_errors():
        _section("Symbol table", format_symbols(res.symbols))
    if show_ir and res.ir is not None:
        _section("Three-address code", format_ir(res.ir))
    if show_code and res.code is not None:
        _section("Stack-machine code", format_code(res.code))

    diags = res.diagnostics.sorted()
    if args.no_warnings:
        diags = [d for d in diags if d.severity == "error"]
    if diags:
        print(format_diagnostics(diags, source, args.file), file=sys.stderr)
    if res.diagnostics.has_errors():
        n = len(res.diagnostics.errors)
        print("%s: %d error%s; compilation failed." % (args.file, n, "" if n == 1 else "s"),
              file=sys.stderr)
        return EXIT_COMPILE

    if args.check:
        print("%s: compiled successfully (not run: --check)." % args.file, file=sys.stderr)
        return EXIT_OK

    if any_stage:
        print("=== Program output ===")
    prompt = sys.stderr if (args.input is None and sys.stdin.isatty()) else None
    if args.input is not None:
        reader = InputReader.from_text(args.input)
    else:
        reader = InputReader(sys.stdin, prompt_stream=prompt)
    out = OutputWriter(sys.stdout)
    try:
        if args.backend == "vm":
            VM(res.code, reader, out, args.max_steps,
               sys.stderr if args.trace else None).run()
        else:
            interpret_tac(res.ir, reader, out, args.max_steps)
    except TinyRuntimeError as exc:
        sys.stdout.flush()
        print(exc.format(args.file), file=sys.stderr)
        return EXIT_RUNTIME
    return EXIT_OK
