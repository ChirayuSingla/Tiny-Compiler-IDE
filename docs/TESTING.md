# Testing and verification

Original compiler baseline: **198 tests passed**. The core desktop IDE passed **218 tests** before optional extensions. The application including real-time compilation passed **272 tests, zero skips** on Windows on 19 October 2026. Exact environment, duration, command and timestamp are in `test-results.json`; the complete log is `tests/latest-results.txt`.

## Reproduce

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe tools\verify_project.py
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe tools\verify_gui.py
```

Install `requirements.txt` first. `verify_project.py` saves the executed log and JSON. `verify_gui.py` launches the native window and records screenshots/assertions. Without PySide6 the GUI test class is skipped; such a run is not desktop verification.

| Area | Executed checks |
|---|---|
| Original compiler and CLI | 198 lexer, parser, semantic, IR, codegen/VM and end-to-end tests |
| Stage/session API | 3 tests: event order, partial failures, snapshot consistency and staleness |
| Qt integration | 17 tests using real widgets, workers and queued signals |
| Same run | Tokens, AST, types, symbols, IR, VM and output compared with one retained result; IR/code regenerated and VM executed independently |
| Compile errors | Lexical/syntax/semantic failures preserve prior stages and partial semantic symbols |
| Runtime errors | Division by zero preserves preceding output; invalid input and instruction limits |
| Input | Int/bool values, multiple values and prompts, blank lines, output before prompts |
| Navigation | All selectors during compilation, an input wait and after execution; terminal/run ID unchanged |
| Source changes | Editing during execution marks results stale without changing code; reverting clears staleness |
| Lifecycle | Save/reopen, New, samples, unsaved cancel, clear output, stop/restart, close during input wait |
| Internal failure | Exceptions are shown without crashing the GUI |
| Example parity | All nine valid original programs run through the GUI worker against expected fixtures |
| Visualizations | 9 CFG/trace/widget tests: real IR edges, IP/state/output, failure capture, bounded history, search and stale estimates |
| Smart editor | 9 engine/widget tests: grammar contexts, scope/shadowing, keywords, operators, templates, keyboard acceptance, pairs, indentation, hover and real diagnostics |
| Program Library | 7 fixture/widget tests; all 23 valid library programs run via VM, TAC and GUI actions; all 4 error entries fail as documented |
| Complexity | 14 tests covering linear, nested, logarithmic, constant-space, ambiguous/nonterminating patterns and independence from measured VM steps |
| Real-time/terminal acceptance | 15 tests: all-stage debounce, current compilation reuse, stale-code rejection, revision guards, sequential typed input, streaming, EOF, Stop, colors, responsive timers and concurrent source/runtime identity |

The native launch used Qt platform **windows**. It exercised every sidebar selector, input, semantic failure/staleness, the library, Demo Mode, live pipeline, CFG, instruction trace, O(n^2) nested-loop analysis and the completion popup. It also verified automatic full compilation without execution/terminal changes, cached Run, and sequential values `20` and `22` typed inside the terminal producing `sum = 42`. Sixteen genuine window/popup captures plus `verification.json` are in `screenshots/`. A popup is a separate Qt top-level widget and has its own capture rather than being composited into a fabricated window image.

## Mandatory acceptance scenarios

`tests/test_realtime.py` uses actual Qt widgets, queued worker signals and the real compiler/VM. The following requested scenarios were executed successfully, with additional tests for runtime/source separation and terminal formatting:

| Scenario | Executed test |
|---|---|
| Run requiring input accepts in-app text | `test_read_accepts_typed_terminal_input_and_runs_real_vm` |
| Repeated reads preserve order | `test_multiple_sequential_reads_keep_order_and_request_identity` |
| Output/prompt visible before completion | `test_prompt_and_output_stream_before_program_finishes` |
| Stop during input wait, then run again | `test_stop_while_waiting_rejects_late_input_and_allows_next_run` |
| Edits refresh real stages without running | `test_edit_debounces_and_refreshes_all_real_stage_results_without_running` |
| Run reuses valid current compilation | `test_run_reuses_current_successful_compilation` (compiler call forbidden by mock) |
| Invalid source never executes stale code | `test_syntax_error_cannot_execute_stale_previously_compiled_code` (VM call forbidden by mock) |
| Navigation preserves output and execution | `test_stage_navigation_preserves_terminal_and_does_not_compile_or_run` |
| Rapid edits reject older results | `test_rapid_edits_and_late_results_cannot_replace_latest_revision` |
| GUI remains responsive during compilation/input wait | `test_gui_stays_responsive_during_compilation_and_input_wait` (Qt timer continues) |
| Complete example uses terminal Enter for every read | `test_complete_example_uses_only_in_app_enter_for_every_input` |

Additional checks exercise EOF/invalid typed input, edit-and-compile while an earlier VM waits, repeat-Run guidance, clearing a pending prompt and distinct QTextCharFormat colors. The full suite also covers division-by-zero and all original compiler behavior. Offscreen widget tests and native script assertions are reproducible automation; they are not a human usability study.

## Manual acceptance

Launch `gui.py`; open `examples/gcd.tiny`; Run; enter `84 36`; verify final output `12`. Inspect tokens, AST, symbols, IR and VM while the terminal remains visible. Edit source and verify the stale banner. Try each `invalid_*.tiny` (supply `0` for the runtime example). Run `input_output.tiny` with `3 10 20 30`. Save/Open a temporary file.

## Verification limits

Linux and macOS were not tested. Automated file tests supply dialog paths instead of operating native dialog chrome. No human user study, accessibility audit or performance benchmark was performed. Large source/output can consume memory; compiler cancellation is between passes. Report layout rendering limitations, if any, are stated in the delivery.
