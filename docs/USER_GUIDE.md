# Tiny Compiler IDE user guide

## Start and explore

Launch with `.\.venv\Scripts\python.exe gui.py` after installing requirements. Edit the initial source, use Open, choose a sample, or open Program Library. After a 350 ms edit pause, background compilation updates every compiler stage. F5 compiles immediately. Ctrl+Enter runs the successful exact-current-source compilation, reusing its bytecode if available or compiling first. A failed current compilation never runs old code. Automatic compilation and stage selection never execute the program.

The first eight sidebar entries are Source, Tokens, AST, Semantics, Symbols, IR, VM Code and Execution. Additional entries are Pipeline, CFG, Trace, Program Library and Complexity. Scroll the sidebar if needed. Splitters resize the source, inspection and terminal areas.

## Completion and diagnostics

Suggestions appear for keyword/identifier prefixes. Ctrl+Space also requests syntax and operator choices at the cursor. Arrow keys change the choice, Enter or Tab accepts, and Esc closes the popup. Common statement templates are labelled `[template]`. Placeholder names in templates need editing to fit the program. Completion inserts text only; Compile/Run remain explicit actions.

Only implemented Tiny syntax is offered. After a declaration colon, suggestions are `int` and `bool`; after `read`, visible declared variables are offered. Analyzer symbols are checked against current declaration positions and lexical scopes; an out-of-scope local is excluded. Comments, strings and lexically invalid contexts suppress suggestions. Suggestions are conservative rather than a complete parser-driven language server, and new declarations may appear after the brief background-check delay.

Parentheses, braces and double quotes close automatically. Typing an already-present closing delimiter moves past it. Backspace between an empty supported pair removes both. Enter inside `{}` makes an indented block. Brackets inside comments/strings are ignored when finding matches. Square brackets, single-quoted strings and function calls are unsupported Tiny syntax.

Hover a keyword for grammar help or a variable for type, storage and declaration information. Background compilation underlines errors/warnings and updates the current source, tokens, AST, semantics, symbols, IR, generated code and derived views. Hover a diagnostic line for its message. Compiler messages appear in their inspectors while typing; the terminal keeps program interaction and explicit Compile/Run errors. Standard Undo/Redo, clipboard, selection and file shortcuts remain available.

## Program Library

The dedicated panel groups 27 examples into Beginner, Intermediate and Advanced. Search names, descriptions, difficulties or compiler concepts. Selection shows the source, description, expected output, sample input and intentional-error information.

- **Load into Editor** creates an editable, unsaved copy.
- **Run Example** loads the selected source and executes it using documented sample input, echoed through the terminal input path.
- **Inspect Compilation** loads and compiles without running.

Save asks for a destination for loaded copies. The source fixtures remain unchanged unless you deliberately select their paths in Save As. Unsaved edits are protected by Save/Discard/Cancel. Run/Inspect are disabled while another run is active; Load remains available and marks any running snapshot stale.

The 23 valid examples cover greetings, types, arithmetic, precedence, input, comparisons, conditionals, parity, counters, summation, factorial, tables, Fibonacci, primes, GCD, digit reversal, nested loops, supported pattern output and multi-step calculations. Four Advanced examples intentionally demonstrate lexical, syntax, semantic and runtime errors; their failure is the expected teaching outcome.

## Terminal and input

The terminal always stays below inspection views. Output, prompts, input echo, errors and status records use different colors. Compilation and runtime status labels identify the source revision and show compiling/success/failure and running/waiting/completed/failed. For a `read`, type an int or `true`/`false` in the terminal input field and press Enter or Send input. Several values may share a line. Blank input prompts again. Stop cancels an input wait or VM execution; compiler cancellation is checked between phases. End Input sends EOF and reports the normal VM error when a value is still required. Invalid values fail with the existing typed runtime diagnostic.

New runs keep earlier terminal text. Clear Terminal clears only the display and reprints a pending read prompt. It does not cancel the read or remove retained output from Execution Results. Run during an active execution explains how to supply input or stop; it never starts a competing VM.

You may edit while execution waits. After the debounce, compilation inspectors follow the new source. The original VM keeps its captured code and pending input. Execution Results and Trace retain that runtime's identity, source revision and a visible earlier-source notice. Late compilation or input messages cannot attach to a different revision/execution. Before the new compilation finishes, its preceding snapshot is marked stale. Navigation never restarts compilation or clears terminal history.

### Two sequential inputs entirely inside the IDE

```text
var a: int;
var b: int;
write "Enter first value";
read a;
write "Enter second value";
read b;
write "sum =", a + b;
```

Type or paste this source and wait for Compilation: compiled successfully. Inspect VM Code before running; no output should be produced by typing. Click Run. The first prompt appears in the integrated terminal; enter `20` and press Enter. The second prompt appears; enter `22` and press Enter. The actual VM prints `sum = 42`. Inspect any completed stage without rerunning. This workflow needs no external console, CLI flag or preloaded input file.

## Visualizations

Expand AST nodes and double-click positioned rows to visit source. Search the Symbol Table by any column. The pipeline colors actual statuses; click a node to open its inspector. The symbol table is shown as a product of semantic analysis, not an invented independent compiler pass. Fast phases may finish before their active state is perceptible.

The CFG uses actual IR leaders and jumps. True/false and jump edges include loop back edges and short-circuit conditions. It is a structural graph, not a claim that both branches execute for a particular input. Select blocks for complete instructions. Graphs support panning, Zoom buttons, Fit and Ctrl+wheel.

Trace rows show real completed or failed instructions, their IP/next IP, line, variable and temporary values, stack and output delta. Selecting a row shows accumulated captured output and highlights the corresponding current source line. Navigation into edited/stale source is suppressed. Trace controls replay retained history only; they do not resume an actual paused VM or produce new output. Replay pauses when its view is hidden.

Capture stops after 2,000 instructions; the actual program continues. Per-row state is bounded to 256 memory entries, the most recent 256 stack entries and 4,096 output characters. A label marks limits. This is intended for educational traces rather than unrestricted production debugging.

## Academic demonstration

1. Enable Demo Mode and choose Sum of first N numbers in Program Library.
2. Click Run Example. Its sample input is 5 and its actual output is 15.
3. Demo Mode selects the pipeline. Inspect tokens, the AST, symbols, IR and VM code without rerunning.
4. Open Trace and use Replay Step/Continue/Reset to explain IP, state and source lines.
5. Open Complexity. The estimate is O(n) in the stated scalar-operation model, separate from the measured instruction count.
6. Run Nested loops and compare its CFG and O(n^2) estimate. Run Number reversal for the supported logarithmic shrinkage pattern.
7. Run GCD or Prime number checker to show an intentionally unresolved complexity case; the compiler and VM still execute these programs correctly.
8. Run an error demonstration and show the failed stage, preserved earlier results and terminal diagnostic.

## Complexity interpretation

The view explains every recognized loop, nesting depth, inferred bound, assumptions and confidence. It supports a narrow, proven set of monotone recurrences and invariant bounds. It uses input value magnitudes, not the byte length of their text. O(1) scalar slots is not an exact memory bound: arbitrary-precision integers can grow, and IDE output/trace buffers are excluded. Unsupported patterns display Unable to determine. See COMPLEXITY.md for the exact supported subset.
