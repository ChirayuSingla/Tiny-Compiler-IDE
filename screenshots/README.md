# Screenshots

This folder is for **real screenshots** of the compiler running. No screenshot has been
captured yet, so none are included here, and the Word report contains clearly labelled
placeholders instead.

To add them (about 5 minutes), run these commands in PowerShell from the repository root and
take a screenshot of each terminal window:

| File to save | Command |
|---|---|
| `01_hello_all_stages.png` | `python main.py examples/hello.tiny --all` |
| `02_arithmetic_run.png` | `python main.py examples/arithmetic.tiny` |
| `03_loop_ir_and_code.png` | `python main.py examples/loop.tiny --ir --code` |
| `04_input_output.png` | `python main.py examples/input_output.tiny --input "4 10 20 30 45"` |
| `05_syntax_errors.png` | `python main.py examples/invalid_syntax.tiny` |
| `06_semantic_errors.png` | `python main.py examples/invalid_semantics.tiny` |
| `07_test_suite.png` | `python -m unittest discover -s tests -t . -v` |

Then insert them in the report under the "Screenshots" section (replace the placeholder
paragraphs), and commit the image files.
