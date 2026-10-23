"""Real Qt event-loop integration tests; run with QT_QPA_PLATFORM=offscreen in CI."""
import copy
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tiny_compiler.codegen import format_code, generate_code
from tiny_compiler.ir import format_ir, generate_ir
from tiny_compiler.pipeline import compile_source
from tiny_compiler.runtime import InputReader
from tiny_compiler.vm import VM
from tiny_compiler.ide.session import RunSession

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from tiny_compiler.ide.window import MainWindow
    from tiny_compiler.ide.worker import CompilerWorker
    HAS_QT = True
except ImportError:
    HAS_QT = False


class StageApiTests(unittest.TestCase):
    def test_pipeline_events_retain_same_run_and_real_artifacts(self):
        events = []
        result = compile_source("var x: int = 7; write x * 6;",
                                lambda stage, status, res: events.append((stage, status, copy.deepcopy(res))))
        self.assertTrue(result.ok)
        completed = [s for s, state, _ in events if state == "completed"]
        self.assertEqual(completed, ["source", "lexical", "syntax", "semantic", "symbols", "ir", "code"])
        parsed = next(r for s, state, r in events if s == "syntax" and state == "completed")
        self.assertIsNone(parsed.ast.statements[1].items[0].type)
        self.assertEqual(result.ast.statements[1].items[0].type, "int")
        self.assertEqual(format_ir(result.ir), format_ir(generate_ir(result.ast)))
        self.assertEqual(result.code, generate_code(result.ir))
        self.assertEqual(VM(result.code).run().getvalue(), "42\n")

    def test_failure_stops_pipeline_and_preserves_partial_results(self):
        for source, failing in (("write @;", "lexical"), ("write 1", "syntax"),
                                ("var x: int = true;", "semantic")):
            with self.subTest(stage=failing):
                events = []
                res = compile_source(source, lambda s, state, r: events.append((s, state)))
                self.assertIn((failing, "error"), events)
                self.assertFalse(res.ok)
                self.assertIsNone(res.code)
                self.assertIsNotNone(res.tokens)
                if failing == "semantic":
                    self.assertIsNotNone(res.symbols)
                    self.assertIn(("symbols", "partial"), events)

    def test_staleness_is_relative_to_compiled_snapshot(self):
        state = RunSession("write 1;")
        self.assertTrue(state.stale("write 2;"))
        self.assertFalse(state.stale("write 1;"))


@unittest.skipUnless(HAS_QT, "Install requirements.txt to run desktop integration tests")
class IdeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window.busy:
            self.window.stop()
            self.wait_for(lambda: not self.window.busy)
        self.window.editor.document().setModified(False)
        self.window.close()
        self.app.processEvents()

    def wait_for(self, condition, seconds=10):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.assertTrue(condition(), "Timed out waiting for Qt worker/UI state")
        self.app.processEvents()

    def run_program(self, source, execute=True):
        self.window.editor.setPlainText(source)
        self.window.start_compile(execute)
        self.wait_for(lambda: not self.window.busy)
        return self.window.session

    def test_same_compilation_populates_every_view_and_vm_output(self):
        session = self.run_program('var x: int = 7; write "answer", x * 6;')
        views = self.window.inspectors
        self.assertTrue(session.result.ok)
        self.assertEqual(session.output, "answer 42\n")
        self.assertIn(session.output, self.window.terminal.toPlainText())
        self.assertIn("Completed program", self.window.terminal.toPlainText())
        self.assertEqual(views.source.toPlainText(), session.source)
        self.assertEqual(views.tokens.rowCount(), len(session.result.tokens))
        for i, token in enumerate(session.result.tokens):
            self.assertEqual(views.tokens.item(i, 1).text(), token.type)
            self.assertEqual(views.tokens.item(i, 2).text(), repr(token.lexeme))
        self.assertEqual(views.ast.topLevelItem(0).text(0), "Program")
        self.assertIn("VarRef x : int", views.semantic.toPlainText())
        self.assertEqual(views.symbols.item(0, 3).text(), session.result.symbols.all_symbols[0].unique)
        self.assertEqual(views.ir.toPlainText(), format_ir(session.result.ir))
        self.assertEqual(views.code.toPlainText(), format_code(session.result.code))
        self.assertEqual(VM(session.result.code).run().getvalue(), session.output)
        self.assertTrue(all(value == "completed" for value in session.statuses.values()))
        output = self.window.terminal.toPlainText()
        identity = session.run_id
        for index in range(8):
            self.window.stage_list.setCurrentRow(index)
            self.app.processEvents()
            self.assertEqual(self.window.stack.currentIndex(), index)
            self.assertEqual(self.window.terminal.toPlainText(), output)
            self.assertEqual(self.window.session.run_id, identity)

    def test_compile_only_then_run_and_persistent_terminal(self):
        self.run_program('write "first";')
        transcript = self.window.terminal.toPlainText()
        session = self.run_program('write "second";', execute=False)
        self.assertEqual(session.statuses["execution"], "not run")
        self.assertEqual(self.window.terminal.toPlainText(), transcript)
        self.assertEqual(session.output, "")
        self.window.actions["run"].trigger()
        self.wait_for(lambda: not self.window.busy)
        self.assertTrue(self.window.terminal.toPlainText().startswith(transcript))
        self.assertIn("second\n", self.window.terminal.toPlainText())

    def test_input_and_stage_navigation_during_execution(self):
        source = 'var n: int; var b: bool; read n; read b; write n + 1, b;'
        self.window.editor.setPlainText(source)
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.assertTrue(self.window.busy)
        before = self.window.terminal.toPlainText()
        for index in range(8):
            self.window.stage_list.setCurrentRow(index)
            self.app.processEvents()
            self.assertEqual(self.window.stack.currentIndex(), index)
            self.assertEqual(self.window.terminal.toPlainText(), before)
        self.window.input_field.setText("41 true")
        QTest.keyClick(self.window.input_field, Qt.Key.Key_Return)
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.output, "42 true\n")
        self.assertEqual(self.window.session.memory["n"], 41)
        self.assertIn("read n> 41 true\n42 true\n", self.window.terminal.toPlainText())

    def test_blank_input_and_multiple_prompts(self):
        self.window.editor.setPlainText("var a: int; var b: int; read a; read b; write a + b;")
        self.window.start_compile(True)
        for text in ("", "20", "22"):
            self.wait_for(lambda: self.window.input_field.isEnabled())
            self.window.input_field.setText(text)
            self.window.send_input()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.output, "42\n")

    def test_compile_errors_preserve_completed_stages(self):
        for source, failure, prior in (("write @;", "lexical", "source"),
                                       ("write 1", "syntax", "lexical"),
                                       ("var x: int = true;", "semantic", "syntax")):
            with self.subTest(stage=failure):
                session = self.run_program(source)
                self.assertEqual(session.statuses[failure], "error")
                self.assertEqual(session.statuses[prior], "completed")
                self.assertEqual(session.statuses["code"], "blocked")
                self.assertIn(failure + " error", self.window.terminal.toPlainText())
                self.assertIsNone(session.result.code)
                self.assertGreater(self.window.inspectors.tokens.rowCount(), 0)
                if failure == "semantic":
                    self.assertEqual(session.statuses["symbols"], "partial")
                    self.assertEqual(self.window.inspectors.symbols.rowCount(), 1)

    def test_runtime_error_retains_output_and_compiler_results(self):
        session = self.run_program('var z: int = 0; write "before"; write 10 / z;')
        self.assertTrue(session.result.ok)
        self.assertEqual(session.statuses["code"], "completed")
        self.assertEqual(session.statuses["execution"], "error")
        self.assertEqual(session.output, "before\n")
        self.assertIn("division by zero", session.runtime_error)
        self.assertIn("before\n", self.window.terminal.toPlainText())
        self.assertIn("division by zero", self.window.inspectors.execution.toPlainText())

    def test_invalid_input_reports_actual_runtime_diagnostic(self):
        self.window.editor.setPlainText("var x: int; read x; write x;")
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.window.input_field.setText("abc")
        self.window.send_input()
        self.wait_for(lambda: not self.window.busy)
        self.assertIn("invalid integer input", self.window.session.runtime_error)

    def test_edits_during_run_are_stale_and_do_not_change_execution(self):
        source = "var x: int; read x; write x + 1;"
        self.window.editor.setPlainText(source)
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        run_id = self.window.session.run_id
        self.window.editor.setPlainText('write "changed";')
        self.assertTrue(self.window.stale_banner.isVisible())
        self.window.input_field.setText("9")
        self.window.send_input()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.output, "10\n")
        self.assertEqual(self.window.session.run_id, run_id)
        self.assertEqual(self.window.inspectors.source.toPlainText(), source)
        self.window.editor.setPlainText(source)
        self.assertFalse(self.window.stale_banner.isVisible())
        self.window.editor.setPlainText('write "new";')
        self.window.start_compile(True)
        self.wait_for(lambda: not self.window.busy)
        self.assertFalse(self.window.stale_banner.isVisible())
        self.assertNotEqual(self.window.session.run_id, run_id)

    def test_stop_waiting_for_input_and_restart(self):
        self.window.editor.setPlainText("var x: int; read x;")
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.window.stop()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.statuses["execution"], "cancelled")
        self.assertFalse(self.window.input_field.isEnabled())
        self.assertEqual(self.run_program("write 42;").output, "42\n")

    def test_close_while_waiting_stops_worker(self):
        self.window.editor.setPlainText("var x: int; read x;")
        self.window.editor.document().setModified(False)
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.window.close()
        self.wait_for(lambda: not self.window.isVisible())
        self.assertFalse(self.window.worker.isRunning())

    def test_stop_loop_and_instruction_limit(self):
        worker = CompilerWorker("while (true) {}", execute=True, max_steps=10)
        sessions = []
        worker.completed.connect(sessions.append)
        worker.start()
        self.wait_for(lambda: not worker.isRunning())
        self.wait_for(lambda: bool(sessions))
        self.assertIn("possible infinite loop", sessions[0].runtime_error)
        self.window.editor.setPlainText("while (true) {}")
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.session.statuses["execution"] == "active")
        self.window.stop()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.statuses["execution"], "cancelled")

    def test_new_open_save_sample_and_clear_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "saved.tiny"
            self.window.editor.setPlainText("write 42;")
            with patch("tiny_compiler.ide.window.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                self.assertTrue(self.window.save_file())
            self.assertEqual(path.read_text(encoding="utf-8"), "write 42;")
            self.window.new_file()
            self.assertEqual(self.window.editor.toPlainText(), "")
            self.assertTrue(self.window.load_path(path))
            self.window.actions["run"].trigger()
            self.wait_for(lambda: not self.window.busy)
            self.assertEqual(self.window.session.output, "42\n")
            self.window.actions["clear"].trigger()
            self.assertEqual(self.window.terminal.toPlainText(), "")
            self.assertEqual(self.window.session.output, "42\n")
            self.window.load_sample(1)
            self.assertIsNone(self.window.path)
            self.assertIn("var", self.window.editor.toPlainText())

    def test_unsaved_cancel_preserves_source(self):
        self.window.editor.insertPlainText("// unsaved\n")
        source = self.window.editor.toPlainText()
        with patch("tiny_compiler.ide.window.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.window.new_file()
        self.assertEqual(self.window.editor.toPlainText(), source)

    def test_all_existing_valid_examples_through_gui_worker(self):
        from tests.test_end_to_end import VALID, input_for, example, read
        for name in VALID:
            with self.subTest(example=name):
                self.window.editor.setPlainText(read(example(name, ".tiny")))
                self.window.start_compile(True)
                text = input_for(name)
                if text:
                    self.wait_for(lambda: self.window.input_field.isEnabled())
                    self.window.input_field.setText(text.replace("\n", " "))
                    self.window.send_input()
                self.wait_for(lambda: not self.window.busy)
                self.assertEqual(self.window.session.output, read(example(name, ".expected")))
                self.assertEqual(self.window.session.statuses["execution"], "completed")

    def test_internal_error_does_not_crash_gui(self):
        with patch("tiny_compiler.pipeline.generate_ir", side_effect=ValueError("test failure")):
            session = self.run_program("write 1;")
        self.assertIn("Internal compiler error: ValueError: test failure", session.runtime_error)
        self.assertEqual(session.statuses["ir"], "error")
        self.assertEqual(session.statuses["code"], "blocked")

    def test_output_before_prompt_is_streamed_and_retained(self):
        self.window.editor.setPlainText('var x: int; write "Enter value"; read x; write x;')
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.assertIn("Enter value\n[Waiting for input: x]\nread x> ", self.window.terminal.toPlainText())
        self.assertEqual(self.window.session.output, "Enter value\n")
        self.window.input_field.setText("42")
        self.window.send_input()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.inputs, ["42"])
        self.assertEqual(self.window.session.output, "Enter value\n42\n")

    def test_navigation_is_available_while_compile_worker_is_active(self):
        import tiny_compiler.ide.worker as worker_module
        actual = worker_module.compile_source
        from threading import Event
        reached = Event()
        release = Event()

        def paused(source, callback):
            def observe(key, status, result):
                callback(key, status, result)
                if key == "syntax" and status == "active":
                    reached.set()
                    release.wait(5)
            return actual(source, observe)

        with patch.object(worker_module, "compile_source", paused):
            self.window.editor.setPlainText("write 42;")
            self.window.append_terminal("existing output\n")
            self.window.stage_list.setCurrentRow(4)
            self.window.start_compile(False)
            try:
                self.wait_for(reached.is_set)
                self.wait_for(lambda: self.window.session.statuses["syntax"] == "active")
                self.assertEqual(self.window.stage_list.currentRow(), 4)
                for index in range(8):
                    self.window.stage_list.setCurrentRow(index)
                    self.assertEqual(self.window.stack.currentIndex(), index)
                    self.assertEqual(self.window.terminal.toPlainText(), "existing output\n")
            finally:
                release.set()
            self.wait_for(lambda: not self.window.busy)


if __name__ == "__main__":
    unittest.main()
