# Architecture

## Pipeline

```
 source.tiny
     |
     v
 +-----------+   tokens    +----------+    AST     +-----------------+
 |  Lexer    | ----------> |  Parser  | ---------> | Semantic        |
 | lexer.py  |             | parser.py|            | analysis        |
 +-----------+             +----------+            | semantic.py     |
     |  lexical errors         | syntax errors     | symbol_table.py |
     v                         v                   +-----------------+
 +----------------------------------------+              | annotated AST
 |  DiagnosticBag (diagnostics.py)        | <------------+ semantic errors
 |  line:col, source line + caret         |              v
 +----------------------------------------+        +-----------+  TAC   +-------------+
                                                    | IR gen    | -----> | Code gen    |
                                                    | ir.py     |        | codegen.py  |
                                                    +-----------+        +-------------+
                                                          |                    | stack code
                                                          v                    v
                                                   +-------------+      +-------------+
                                                   | TAC         |      | Stack VM    |
                                                   | interpreter |      | vm.py       |
                                                   | (ir.py)     |      +-------------+
                                                   +-------------+            |
                                                          \____ runtime.py ____/   program output
                                                             (shared semantics)
```

`pipeline.py` chains the phases (`compile_source`, `run_source`); `cli.py` is the
command-line front end (`main.py` and `python -m tiny_compiler` are thin entry points).

## Modules

| Module | Responsibility | Input -> Output |
|---|---|---|
| `lexer.py` | Hand-written scanner. Tracks line/column, skips comments, decodes string escapes, reports invalid characters and keeps scanning | `str` -> `List[Token]` |
| `ast_nodes.py` | Dataclass AST nodes (`Program`, `VarDecl`, `Assign`, `If`, `While`, `Read`, `Write`, `Block`, `IntLit`, `BoolLit`, `StringLit`, `VarRef`, `Unary`, `Binary`) plus the tree printer | - |
| `parser.py` | Recursive-descent parser (one method per grammar rule), panic-mode recovery at `;` / `}` | `List[Token]` -> `Program` |
| `symbol_table.py` | Stack of scopes; unique storage name per declared variable (`x`, `x#1`, ...) so shadowing is resolved once, in the front end | - |
| `semantic.py` | Declaration / scope checks, type checking, constant-zero-divisor detection, unused-variable warnings; annotates every expression with its type and every name with its `Symbol` | `Program` -> `SymbolTable` + diagnostics |
| `ir.py` | Three-address-code generator, text formatter and an independent TAC interpreter | annotated `Program` -> `List[Instr]` |
| `codegen.py` | Translates TAC into stack-machine bytecode; resolves labels to instruction indexes | `List[Instr]` -> `List[VMInstr]` |
| `vm.py` | Stack VM with memory dictionary, step limit and optional execution trace | `List[VMInstr]` -> output |
| `runtime.py` | Arithmetic (truncating `/`, `%`), value formatting, `InputReader`, `OutputWriter` shared by both back-ends | - |
| `diagnostics.py` | `Diagnostic`, `DiagnosticBag`, `CompileError`, `TinyRuntimeError`, caret rendering | - |
| `pipeline.py` | Orchestration, stops after the first failing phase | `str` -> `CompilationResult` |
| `cli.py` | Argument parsing, stage dumps, exit codes | - |

## Design decisions

1. **Recursive descent** - the grammar is small and LL(1); each rule maps to one method, which
   keeps the parser readable for a student report and easy to extend with good error messages.
2. **Typed language (`int`, `bool`)** - gives the semantic phase real work (type checking of
   conditions, operators and assignments) without needing a large language.
3. **Unique storage names in the front end** - the symbol table gives each declaration a unique
   name, so later phases never think about scopes.
4. **TAC then stack code** - TAC is the classical, easily-inspected IR (temporaries `$tN`, labels
   `LN`); the stack VM is a simple, documented target that really executes. Native machine code
   is out of scope and is **not** claimed.
5. **Two execution back-ends sharing `runtime.py`** - the TAC interpreter and the VM implement the
   same semantics through the same helper functions; the test-suite runs every example on both and
   compares the output. This acts as a cross-check of code generation.
6. **Short-circuit `and` / `or`** are lowered to conditional jumps in the IR, not to a BIN op.
7. **Errors as data** - phases append `Diagnostic`s to a bag instead of raising, so one run can
   report many problems; the pipeline stops between phases so later phases never see invalid
   input.
8. **Safety net** - the VM aborts after `--max-steps` instructions so infinite loops terminate.

## Adding a feature (extension guide)

New operator: add the token in `lexer.py`, a precedence level in `parser.py`, its typing rule in
`semantic.py::_binary`, an entry in `runtime.apply_binary`, and the `BIN_TO_OP` table in
`codegen.py`; add tests at each level.
