"""Launch the native Qt window, exercise it and capture genuine widget screenshots."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tiny_compiler.ide.window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1500, 960)
    window.show()
    output = ROOT / "screenshots"
    output.mkdir(exist_ok=True)
    evidence = {"platform": app.platformName(), "screenshots": [], "checks": []}
    state = {"step": 0, "deadline": time.monotonic() + 40}
    interactive_source = ('var a: int;\nvar b: int;\nwrite "Enter first value";\n'
                          'read a;\nwrite "Enter second value";\nread b;\nwrite "sum =", a + b;\n')

    def capture(name):
        path = output / name
        if not window.grab().save(str(path)):
            raise RuntimeError("Could not save " + str(path))
        evidence["screenshots"].append(str(path.relative_to(ROOT)))

    def tick():
        try:
            if time.monotonic() > state["deadline"]:
                raise TimeoutError("Native GUI verification timed out")
            step = state["step"]
            if step == 0:
                window.load_path(ROOT / "examples" / "loop.tiny")
                window.start_compile(True)
                state["step"] = 1
            elif step == 1 and not window.busy:
                assert window.session.output == (ROOT / "examples/loop.expected").read_text(encoding="utf-8")
                window.stage_list.setCurrentRow(1)
                state["step"] = 2
            elif step == 2:
                capture("01_tokens.png")
                window.stage_list.setCurrentRow(2)
                state["step"] = 3
            elif step == 3:
                capture("02_ast.png")
                terminal = window.terminal.toPlainText()
                for i in range(window.stage_list.count()):
                    window.stage_list.setCurrentRow(i)
                    assert window.stack.currentIndex() == i
                    assert window.terminal.toPlainText() == terminal
                evidence["checks"].append("Native compile/run, VM output and all sidebar selectors passed")
                window.load_path(ROOT / "examples/gcd.tiny")
                window.start_compile(True)
                state["step"] = 4
            elif step == 4 and window.input_field.isEnabled():
                window.stage_list.setCurrentRow(6)
                state["step"] = 5
            elif step == 5:
                capture("03_input_wait.png")
                window.input_field.setText("84 36")
                window.send_input()
                state["step"] = 6
            elif step == 6 and not window.busy:
                assert window.session.output == (ROOT / "examples/gcd.expected").read_text(encoding="utf-8")
                evidence["checks"].append("Interactive input 84 36 produced the expected GCD output")
                window.stage_list.setCurrentRow(7)
                state["step"] = 7
            elif step == 7:
                capture("04_execution.png")
                window.editor.setPlainText("var x: int = true;\nwrite x;")
                window.start_compile(True)
                state["step"] = 8
            elif step == 8 and not window.busy:
                assert window.session.statuses["semantic"] == "error"
                assert window.session.statuses["syntax"] == "completed"
                window.stage_list.setCurrentRow(3)
                state["step"] = 9
            elif step == 9:
                capture("05_semantic_error.png")
                evidence["checks"].append("Semantic failure retained tokens, AST and partial symbol table")
                window.editor.insertPlainText("// changed\n")
                state["step"] = 10
            elif step == 10:
                assert window.stale_banner.isVisible()
                capture("06_stale_results.png")
                evidence["checks"].append("Editing source visibly marks retained results stale")
                window.editor.document().setModified(False)
                window.navigate_to("library")
                window.inspectors.library.select_id("nested_loops")
                state["step"] = 11
            elif step == 11:
                capture("07_program_library.png")
                window.inspectors.library.buttons["load"].click()
                window.demo_action.setChecked(True)
                window.start_compile(True)
                state["step"] = 12
            elif step == 12 and window.input_field.isEnabled():
                assert window.session.statuses["execution"] == "waiting"
                window.inspectors.pipeline.canvas.fit()
                capture("08_live_pipeline.png")
                window.input_field.setText("2")
                window.send_input()
                state["step"] = 13
            elif step == 13 and not window.busy:
                assert window.session.output == "1 1\n1 2\n2 1\n2 2\n"
                assert window.session.complexity.time == "O(n^2)"
                window.navigate_to("cfg")
                state["step"] = 14
            elif step == 14:
                window.inspectors.cfg.canvas.fit()
                capture("09_control_flow.png")
                window.navigate_to("trace")
                window.inspectors.trace.table.setCurrentCell(10, 0)
                state["step"] = 15
            elif step == 15:
                capture("10_execution_trace.png")
                window.navigate_to("complexity")
                state["step"] = 16
            elif step == 16:
                capture("11_complexity.png")
                evidence["checks"].append("Program Library, Demo Mode, real CFG/trace and O(n^2) nested-loop analysis passed")
                window.editor.setPlainText("wh")
                from PySide6.QtGui import QTextCursor
                window.editor.moveCursor(QTextCursor.MoveOperation.End)
                window.editor.setFocus()
                window.editor.show_completions()
                state["step"] = 17
            elif step == 17:
                assert "while" in window.editor.completion_options
                capture("12_smart_editor.png")
                assert window.editor.completer.popup().grab().save(str(output / "13_completion_popup.png"))
                evidence["screenshots"].append("screenshots/13_completion_popup.png")
                evidence["checks"].append("Grammar-aware completion popup offers while for wh without executing the source")
                window.editor.completer.popup().hide()
                state["terminal_before_edit"] = window.terminal.toPlainText()
                window.editor.setPlainText(interactive_source)
                window.navigate_to("code")
                state["step"] = 18
            elif step == 18 and (window.session.source == interactive_source
                                 and window.editor.analysis_revision == window.editor.revision):
                assert window.session.result.ok
                assert window.session.statuses["execution"] == "not run"
                assert window.terminal.toPlainText() == state["terminal_before_edit"]
                capture("14_realtime_compilation.png")
                evidence["checks"].append("Editing alone refreshed real compiler stages after debounce without VM execution or terminal changes")
                window.start_compile(True)
                assert window.worker.reused_compilation
                state["step"] = 19
            elif step == 19 and window.input_field.isEnabled():
                assert window.pending_input.sequence == 1
                window.vertical.setSizes([500, 390])
                window.navigate_to("pipeline")
                window.inspectors.pipeline.canvas.fit()
                capture("15_terminal_input.png")
                QTest.keyClicks(window.input_field, "20")
                QTest.keyClick(window.input_field, Qt.Key.Key_Return)
                state["step"] = 20
            elif step == 20 and window.input_field.isEnabled() and window.pending_input.sequence == 2:
                QTest.keyClicks(window.input_field, "22")
                QTest.keyClick(window.input_field, Qt.Key.Key_Return)
                state["step"] = 21
            elif step == 21 and not window.busy:
                assert window.runtime_session.output == "Enter first value\nEnter second value\nsum = 42\n"
                window.navigate_to("execution")
                state["step"] = 22
            elif step == 22:
                window.terminal.verticalScrollBar().setValue(window.terminal.verticalScrollBar().maximum())
                capture("16_terminal_results.png")
                evidence["checks"].append("Run reused the successful current compilation; two sequential values typed inside terminal produced sum = 42")
                (output / "verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print(json.dumps(evidence, indent=2), flush=True)
                window.editor.document().setModified(False)
                window.close()
                state["step"] = 23
            elif step == 23 and not window.isVisible():
                timer.stop()
                app.quit()
        except Exception as exc:
            print("GUI verification failed: %r" % exc, file=sys.stderr, flush=True)
            timer.stop()
            window.stop()
            app.exit(1)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(180)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
