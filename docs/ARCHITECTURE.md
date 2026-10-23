# Architecture and workflow

## Backend reuse

```text
Editor snapshot -> pipeline.compile_source(source, on_stage)
  -> lexer.tokenize -> Token[]
  -> parser.parse -> Program AST
  -> semantic.analyze -> annotated AST + SymbolTable
  -> ir.generate_ir -> three-address Instr[]
  -> codegen.generate_code -> stack VMInstr[]
  -> VM(the same result.code) -> runtime InputReader / OutputWriter
```

`CompilationResult` owns source, diagnostics, tokens, AST, symbols, IR and code. Compiler logic stays in its original modules. `compile_source(source)` remains compatible; an optional observer reports progress without importing Qt. The symbol table comes from semantic analysis. Parser recovery and partial semantic declarations remain inspectable after errors.

| Desktop module | Responsibility |
|---|---|
| `ide/window.py` | File actions, splitters, sidebar, status labels and terminal |
| `ide/editor.py` | Source editing, painted line gutter, highlighting and indentation |
| `ide/views.py` | Token/symbol tables, dataclass AST tree, IR/VM and diagnostic views |
| `ide/session.py` | Qt-free run state, queued input, buffered output |
| `ide/worker.py` | QThread owning one compilation and optional VM execution |
| `ide/editor_analysis.py` | Debounced, revision-guarded full compilation without execution |
| `ide/terminal.py` | Literal-text transcript with distinct output, input, prompt, error and status formats |
| `ide/__main__.py`, `gui.py` | Desktop launch and dependency error message |

The main splitter holds source, the selected inspector and right sidebar. A vertical splitter puts the terminal beneath all three. Navigation changes only the `QStackedWidget` index, preserving execution, source and terminal.

## Run lifecycle and ownership

1. Every edit increments `CodeEditor.revision`, invalidates old checks and restarts a 350 ms timer. Automatic compilation captures source, filename, revision and compilation run ID. Explicit Compile/Run claims its revision so duplicate background checks cannot replace it.
2. The service calls the real pipeline. Observers report active/completed/error for every pass, updating all inspectors. Symbol status follows semantic analysis. Automatic compilation never creates a VM or writes to the terminal.
3. Deep-copied sessions cross threads through Qt signals. The semantic analyzer annotates the AST in place, so sharing mutable snapshots would be unsafe. Widgets are updated only in the main thread.
4. On a compilation failure, pending downstream stages become blocked. Earlier results and failed-stage partial data remain available.
5. Run reuses a deep copy of the successful current compilation only when source text and revision both match and code generation completed. Otherwise it compiles the captured source first. Failure blocks execution. The worker runs `VM(session.result.code)` directly, with a fresh `execution_id` even when reusing a compilation ID. Exact output, steps and final memory are recorded even after runtime errors.
6. `window.session` is the newest compilation; `window.runtime_session` is the active or most recent execution. Edits mark preceding results stale, then compilation inspectors follow the new revision. Running code, output and input remain bound to the original execution. Runtime views identify earlier source explicitly and disable stale source navigation.
7. Revision plus exact-source checks reject late automatic snapshots. Worker-identity checks reject obsolete explicit-worker signals. Runtime trace batches use execution IDs. Results survive completion, navigation and terminal clearing; there is no automatic program execution. At most one explicit compiler/VM worker and one editor compilation thread coexist.

## Input and output

`InteractiveReader` subclasses the existing `InputReader`, reusing int/bool validation. Token retrieval waits on a thread-safe queue in the worker, checking cancellation every 50 ms. A typed `InputRequest(execution_id, sequence, name)` signal enables the terminal field. Enter/Send input submits a line with the request token; a lock rejects duplicates, cancelled requests and late replies from another execution. Whitespace-separated pending values supply subsequent reads. Blank input prompts again; invalid values raise the existing runtime error. End Input submits a None sentinel and reuses the VM's standard input-exhausted diagnostic. Stop releases waits via cancellation; it does not terminate a thread forcibly.

`StreamingWriter` retains exact output and batches display signals at about 30 ms or 4096 characters, flushing before input waits, errors and completion. `Terminal` inserts literal text with role-based QTextCharFormats, without HTML interpretation. Prompts, input echo and lifecycle records appear only in the transcript; `session.output` contains program output. Clear Terminal does not touch queues, compiler results or retained output. No global stdin/stdout redirection or external console is used.

## Cancellation and statuses

Stop sets a threading event. Compiler observers check it between passes; the VM's optional `should_stop` callback checks every instruction. Closing during execution requests cancellation and waits asynchronously for `QThread.finished`. Threads are never forcibly terminated. Save/Discard/Cancel protects unsaved source.

Compiler states normally follow pending -> active -> completed. Failures become error and block downstream stages; symbols may be partial. Execution supports active, waiting, completed, error, cancelled and not run. Fast stages may finish before their active status can be observed; no artificial delays are introduced.

## Boundaries and verification

The compiler is independent of PySide6. Pipeline and VM changes are optional callbacks; lexing, parsing, type rules, scopes, lowering, short-circuiting and arithmetic remain unchanged. The target is a VM, and the syntax view is an AST rather than a concrete parse tree containing punctuation.

## Visualizations and trace

`control_flow.py` partitions actual IR leaders into basic blocks, maps jump labels to owners and derives structural edges. `ide/visuals.py` renders this graph and the live eight-stage pipeline in native QGraphicsView canvases. Pipeline topology represents actual dependencies, including semantic analysis producing symbols. No Graphviz, web view or plotting dependency is required.

`VM.on_step` optionally emits `execution_trace.TraceStep` after each instruction, or at a failed instruction. It includes actual IP/next IP, instruction, source line, state and output delta. A callback returning False disables capture without stopping execution. The GUI worker batches trace signals and retains the first 2,000 rows with bounded per-row state. The existing CLI text `--trace` remains unchanged. Replay Step/Continue/Reset navigate captured records without invoking the VM. Symbols gain a search field over the existing table.

`NAVIGATION` extends the eight compiler `STAGES` with pipeline, CFG, trace, library and complexity. These are inspection/tools views rather than fabricated additional compiler passes. Compilation views use one current RunSession; runtime/trace views use the separately labelled runtime RunSession. They preserve source identity and stale-source indication.

## Smart editor service

`completion.py` derives supported candidates from Tiny grammar contexts and analyzer symbols, filtered by current declaration identity, source position and lexical scope. The QCompleter inserts only an accepted prefix replacement. It offers no callable functions or unsupported language constructs. Templates are editable statement text.

`ide/editor_analysis.py` runs a separately owned debounced QThread through code generation and derives CFG/complexity from that same result. For partial syntax, recovered AST declarations are deep-copied and analyzed with a separate diagnostic bag solely for completion; optional completion recovery cannot mutate or invalidate the actual compilation. Snapshots are accepted only when revision and exact source match the editor. They update the stage inspectors and inline diagnostics, but never write to the terminal or execute code. Only one editor check exists at a time; newer text is checked after an interrupted older task finishes. Closing interrupts between passes and waits asynchronously before releasing the worker.

## Program Library and demo workflow

`program_library.py` reads `examples/library.json` and the 27 source files under `examples/library/`. Metadata stores independently specified expected output and intended diagnostic, not compiler stage data. `ide/library.py` provides categories, concept search, source preview and explicit Load/Run/Inspect actions. Loading makes an unsaved copy with no path to the fixture; Run Example sends sample input through the same interactive terminal queue. Four entries are clearly marked intentional error demonstrations.

Demo Mode selects the pipeline on compile/run. It does not delay stages or invent progress. Trace replay highlights source lines while the captured source is current; editing suppresses cross-navigation and marks retained data stale.

## Optional complexity enrichment

`complexity.py` operates on the semantically annotated AST and storage identities. Conservative abstract dataflow identifies only a documented subset of terminating monotone loops and invariant bounds, composing their upper bounds. `COMPLEXITY.md` specifies the unit-cost scalar model and rejection cases. Runtime measurements never feed the estimate. Scalar-slot space is explicitly distinguished from bit/byte consumption and IDE buffers. Optional CFG/complexity failures are isolated in `enrichment_errors` and cannot invalidate otherwise correct compiled code.

Tests use actual QApplication widgets, QThreads and queued signals. Inspector values are compared with retained compiler objects and independently executed bytecode. A controlled pause verifies navigation during compilation; an actual input wait verifies navigation during execution. All nine existing valid examples also run through the GUI worker. A separate native Windows script launches the application and saves genuine widget screenshots.
