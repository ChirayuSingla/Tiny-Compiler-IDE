# Genuine screenshots

Captured from the implemented application's own window with `MainWindow.grab()` on Qt's native Windows platform, using `tools/verify_gui.py`. All views contain real compilation data.

- `01_tokens.png`: loop program tokens and output.
- `02_ast.png`: expandable AST from that compilation.
- `03_input_wait.png`: VM code while GCD waits for input.
- `04_execution.png`: execution after entering `84 36`.
- `05_semantic_error.png`: semantic error and partial results.
- `06_stale_results.png`: retained results after source edits.
- `07_program_library.png`: categorized example browser and source metadata.
- `08_live_pipeline.png`: actual compiler statuses while the VM awaits input.
- `09_control_flow.png`: graph generated from real nested-loop IR.
- `10_execution_trace.png`: retained VM history and source-line navigation.
- `11_complexity.png`: conservative nested-loop estimate and assumptions.
- `12_smart_editor.png`: edited source and retained results marked stale.
- `13_completion_popup.png`: separate genuine capture of the QCompleter popup offering supported while completions. Popups are top-level widgets and are not included by the main window's grab method.
- `14_realtime_compilation.png`: generated instructions updated by typing alone; revision 8 compilation is separate from revision 6's retained runtime.
- `15_terminal_input.png`: current cached compilation running and waiting for the first of two terminal inputs.
- `16_terminal_results.png`: actual `sum = 42` after `20` and `22` were entered sequentially in the terminal field.

The terminal intentionally preserves earlier runs. `verification.json` records executed assertions. Reproduce with `python tools/verify_gui.py`, with `QT_QPA_PLATFORM` unset.
