# Tiny Programming Language Compiler

An educational compiler for a small, C-like **Tiny** language, written in Python (standard
library only). It demonstrates the complete pipeline:

```
Source -> Lexical analysis -> Syntax analysis -> Semantic analysis
       -> Three-address code (IR) -> Stack-machine code -> Execution on a virtual machine
```

> **Honest scope note.** The target of the compiler is a *stack-based virtual machine* that is
> part of this project. It does **not** generate native machine code. The Tiny language here is
> this project's own dialect (there is no single universal "TINY" specification); it is fully
> specified in [docs/LANGUAGE_SPEC.md](docs/LANGUAGE_SPEC.md) and
> [docs/GRAMMAR.md](docs/GRAMMAR.md).

* Requirements: **Python 3.8 or newer**, no third-party packages (developed and tested on
  Python 3.9.0 / Windows 11).
* Word project report: [report/Tiny_Programming_Language_Compiler_Report.docx](report/Tiny_Programming_Language_Compiler_Report.docx)

## Supported language features

| Feature | Details |
|---|---|
| Types | `int` (arbitrary precision), `bool` |
| Declarations | `var x: int;`, `var b: bool = true;` (defaults `0` / `false`), block scope with shadowing |
| Expressions | `+ - * / %`, unary `-`, parentheses, comparisons `== != < <= > >=`, `and` `or` `not` (short-circuit) |
| Statements | assignment, `if` / `else if` / `else`, `while`, nested blocks |
| I/O | `read x;` (int or bool), `write "text", expr, ...;` |
| Comments | `// line` and `/* block */` |
| Diagnostics | lexical, syntax (with error recovery), semantic, run-time errors with line:column and a caret |

Known limitations: no functions, arrays, floats, strings as variables, `for`, `break`/`continue`;
no optimisation pass; native code generation is out of scope; a single source file; integer
division truncates toward zero. These constructs are *rejected with a clear message*, never
silently accepted.

## Setup

### Windows PowerShell

```powershell
git clone https://github.com/Hydra-Of-Malice/Chirayu-Project.git
cd Chirayu-Project
python --version            # must be 3.8 or newer
python main.py examples/hello.tiny
```

If `python` is not found, try `py -3 main.py examples/hello.tiny`.
No `pip install` is needed to run the compiler or the tests.

### Linux / macOS

```bash
git clone https://github.com/Hydra-Of-Malice/Chirayu-Project.git
cd Chirayu-Project
python3 main.py examples/hello.tiny
```

(Use `python3` instead of `python` in all commands below.)

## Usage

```
python main.py FILE [--tokens] [--ast] [--symbols] [--ir] [--code] [--all]
                    [--check] [--backend vm|ir] [--input "TEXT"] [--trace]
                    [--max-steps N] [--no-warnings] [--version]
```

`python -m tiny_compiler FILE ...` is equivalent.

| Option | Effect |
|---|---|
| *(none)* | compile and run, printing only the program output |
| `--tokens` | token stream with line:column |
| `--ast` | abstract syntax tree (expression nodes annotated with their types) |
| `--symbols` | symbol table (name, type, scope depth, storage name, declaration position) |
| `--ir` | three-address code |
| `--code` | generated stack-machine code with instruction indexes |
| `--all` | all of the above, then the program output |
| `--check` | compile only; do not run |
| `--backend ir` | run the three-address code with the reference interpreter instead of the VM |
| `--input "4 10 20"` | supply values for `read` (otherwise read from standard input) |
| `--trace` | print each executed VM instruction and the stack (stderr) |
| `--max-steps N` | abort after `N` executed instructions (default 5,000,000) |

Exit codes: `0` success, `1` compile error, `2` usage error, `3` run-time error, `4` file could
not be read.

### Show every stage of a program

```powershell
python main.py examples/hello.tiny --all
```

```
=== Tokens ===
LOC      TYPE     LEXEME
2:1      write    write
2:7      STRING   "Hello, Tiny!"
2:21     ;        ;
3:1      EOF      <end of file>

=== AST ===
Program
`-- Write
    `-- StringLit 'Hello, Tiny!' : string

=== Symbol table ===
NAME         TYPE   SCOPE  STORAGE        DECLARED  READ?
(no variables declared)

=== Three-address code ===
    write "Hello, Tiny!"
    newline
    halt

=== Stack-machine code ===
0000  PRINT_STR "Hello, Tiny!"
0001  PRINT_NL
0002  HALT

=== Program output ===
Hello, Tiny!
```

## Examples and expected output

Each example has a hand-checked `examples/<name>.expected` file. The test-suite runs every
example and compares the real output with that file, so these outputs are verified, not assumed.

| Run (PowerShell) | Expected output |
|---|---|
| `python main.py examples/hello.tiny` | `Hello, Tiny!` |
| `python main.py examples/arithmetic.tiny` | [arithmetic.expected](examples/arithmetic.expected) (e.g. `a + b * 2      = 13`) |
| `python main.py examples/conditional.tiny` | `FizzBuzz`, `x is negative`, `x is not positive` |
| `python main.py examples/loop.tiny` | `sum of 1..10 = 55`, then `5 4 3 2 1` (one per line) and `liftoff` |
| `Get-Content examples/input_output.input \| python main.py examples/input_output.tiny` | `count = 4`, `sum   = 105`, `average (integer) = 26` |
| `python main.py examples/input_output.tiny --input "4 10 20 30 45"` | same as the line above |
| `python main.py examples/fibonacci.tiny` | `0 1 1 2 3 5 8 13 21 34 55 89` (one per line) |
| `python main.py examples/gcd.tiny --input "84 36"` | `gcd of 84 and 36 is:` / `12` |
| `python main.py examples/scopes.tiny` | block scope and shadowing demo ([scopes.expected](examples/scopes.expected)) |
| `python main.py examples/logic.tiny` | bool and short-circuit demo ([logic.expected](examples/logic.expected)) |

Bash equivalent for stdin: `python3 main.py examples/input_output.tiny < examples/input_output.input`.

### Error examples (must fail with a readable message, never a Python traceback)

| Run | Exit code | What it shows |
|---|---|---|
| `python main.py examples/invalid_character.tiny` | 1 | lexical errors for `@` and `#` |
| `python main.py examples/invalid_syntax.tiny` | 1 | 4 syntax errors reported in one run |
| `python main.py examples/invalid_semantics.tiny` | 1 | duplicate / undeclared / use-before-declaration / type / constant division by zero |
| `python main.py examples/invalid_runtime.tiny --input 0` | 3 | run-time `division by zero` |

Sample (`invalid_syntax.tiny`):

```
examples/invalid_syntax.tiny:2:15: syntax error: expected ';' at the end of the declaration, found identifier 'x'
    2 | var x: int = 5
      |               ^
examples/invalid_syntax.tiny:3:8: syntax error: expected an expression, found ';'
    3 | x = x + ;
      |        ^
...
examples/invalid_syntax.tiny: 4 errors; compilation failed.
```

## Tests

```powershell
python -m unittest discover -s tests -t . -v      # all tests, verbose
python -m unittest discover -s tests -t .         # all tests, quiet
python -m unittest tests.test_parser              # a single module
```

(`pytest` also works if installed: `python -m pytest tests`.)
See [docs/TESTING.md](docs/TESTING.md) for the test plan and the recorded results.

## Project layout

```
Chirayu-Project/
  main.py                    entry point (python main.py FILE)
  tiny_compiler/             the compiler package (lexer, parser, semantic, ir, codegen, vm, ...)
  examples/                  .tiny programs + .expected output (+ .input where needed)
  tests/                     unit, integration and end-to-end tests (unittest)
  docs/                      LANGUAGE_SPEC, GRAMMAR, ARCHITECTURE, TESTING
  report/                    Word project report (.docx)
  screenshots/               how to capture the review screenshots
  tools/build_report.py      regenerates the Word report from the real code and test results
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python: command not found` / opens Microsoft Store | Install Python 3.8+ from python.org, tick "Add to PATH", or use `py -3` |
| `ModuleNotFoundError: tiny_compiler` | Run commands from the repository root (the folder containing `main.py`) |
| `tiny: cannot read '...'` (exit 4) | Wrong path or file name; check the path relative to the current folder |
| `no more input available for 'read x'` | Provide values with `--input "..."` or pipe a file into standard input |
| Program seems to hang waiting | A `read` statement is waiting for keyboard input (a `read x>` prompt is shown on a terminal) |
| `execution stopped after N steps` | An infinite loop, or raise `--max-steps` for a long computation |
| `variable 'x' is not declared` | Declare it first with `var x: int;` |
| `the condition of 'if' must be of type 'bool'` | Use a comparison, e.g. `if (x != 0)`, instead of `if (x)` |
| Non-ASCII text in the source | Only allowed inside string literals and comments |

## 3-5 minute demonstration script (academic review)

1. **(30 s) Problem and pipeline** - show the pipeline diagram in
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): lexer -> parser -> semantic analysis -> TAC ->
   stack code -> VM.
2. **(45 s) The language** - open `examples/loop.tiny`; mention `int`/`bool`, `while`, `if`,
   `read`/`write`, block scope.
3. **(60 s) Compile and run** -
   `python main.py examples/arithmetic.tiny` (point at precedence: `a + b * 2 = 13`,
   truncating division `-7 / 3 = -2`).
4. **(60 s) Show the stages** - `python main.py examples/loop.tiny --tokens --ast --ir --code`;
   explain tokens with positions, the AST, temporaries `$t1` and labels `L1`, and how
   `ifFalse` becomes `JZ`.
5. **(30 s) Input/output** - `python main.py examples/gcd.tiny --input "84 36"` -> `12`.
6. **(45 s) Error handling** - `python main.py examples/invalid_syntax.tiny` (several errors with
   a caret) and `python main.py examples/invalid_semantics.tiny` (type and scope errors).
   Then `python main.py examples/invalid_runtime.tiny --input 0` (run-time error, exit code 3).
7. **(30 s) Verification** - `python -m unittest discover -s tests -t .` and state the number of
   tests that ran and passed.
8. **Close** - limitations (VM target only, no functions/arrays/floats) and future work.

## Documentation

* [docs/LANGUAGE_SPEC.md](docs/LANGUAGE_SPEC.md) - lexical rules, types, scope, semantics
* [docs/GRAMMAR.md](docs/GRAMMAR.md) - EBNF grammar and parsing notes
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - modules, data flow, design decisions
* [docs/TESTING.md](docs/TESTING.md) - test plan and recorded results
