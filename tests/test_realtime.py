"""Mandatory real-time compilation and in-app terminal acceptance tests."""
from copy import deepcopy
from threading import Event
import time
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from tiny_compiler.ide.window import MainWindow
    from tiny_compiler.ide.session import InputRequest
    from tiny_compiler.ide.terminal import COLORS
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "Install requirements.txt")
class RealTimeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()

    def wait_for(self, condition, seconds=12):
        until = time.monotonic() + seconds
        while not condition() and time.monotonic() < until:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertTrue(condition(), "Timed out awaiting compiler/runtime state")
        self.app.processEvents()

    def tearDown(self):
        if self.window.busy:
            self.window.stop()
            self.wait_for(lambda: not self.window.busy)
        self.window.editor.document().setModified(False)
        self.window.close()
        self.wait_for(lambda: not self.window.isVisible())

    def enter(self, value):
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.window.input_field.setFocus()
        QTest.keyClicks(self.window.input_field, value)
        QTest.keyClick(self.window.input_field, Qt.Key.Key_Return)

    def compiled(self, source):
        self.window.editor.setPlainText(source)
        self.wait_for(lambda: self.window.session is not None and
                      self.window.session.source == source and
                      self.window.editor.analysis_revision == self.window.editor.revision and
                      self.window.session.statuses["execution"] in ("not run", "blocked"))
        return self.window.session

    def test_read_accepts_typed_terminal_input_and_runs_real_vm(self):
        source = 'var n: int; read n; write n * n;'
        self.window.editor.setPlainText(source)
        self.window.actions["run"].trigger()
        self.enter("7")
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, "49\n")
        self.assertEqual(self.window.runtime_session.memory["n"], 7)
        transcript = self.window.terminal.toPlainText()
        self.assertIn("read n> 7\n49\n", transcript)
        self.assertIn("Completed program", transcript)
        self.assertIn("completed", self.window.runtime_status.text())

    def test_multiple_sequential_reads_keep_order_and_request_identity(self):
        self.window.editor.setPlainText('var a: int; var b: int; var flag: bool; read a; read b; read flag; write a - b, flag;')
        self.window.start_compile(True)
        ids = []
        for value in ("30", "8", "true"):
            self.wait_for(lambda: self.window.pending_input is not None)
            ids.append(self.window.pending_input)
            self.enter(value)
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, "22 true\n")
        self.assertEqual([request.sequence for request in ids], [1, 2, 3])
        self.assertEqual(len({request.execution_id for request in ids}), 1)

    def test_prompt_and_output_stream_before_program_finishes(self):
        self.window.editor.setPlainText('var n: int; write "Enter a number"; read n; write "Answer", n + 1;')
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.input_field.isEnabled())
        self.assertTrue(self.window.busy)
        self.assertIn("Enter a number\n", self.window.terminal.toPlainText())
        self.assertIn("Waiting for input", self.window.terminal.toPlainText())
        self.assertEqual(self.window.runtime_session.output, "Enter a number\n")
        self.enter("41")
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, "Enter a number\nAnswer 42\n")

    def test_stop_while_waiting_rejects_late_input_and_allows_next_run(self):
        self.window.editor.setPlainText("var n: int; read n; write n;")
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.pending_input is not None)
        request, worker = self.window.pending_input, self.window.worker
        self.window.actions["stop"].trigger()
        self.wait_for(lambda: not self.window.busy)
        self.assertFalse(worker.submit("999", request))
        self.assertFalse(self.window.input_field.isEnabled())
        self.assertIn("Stopped program", self.window.terminal.toPlainText())
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.pending_input is not None)
        self.assertNotEqual(self.window.pending_input.execution_id, request.execution_id)
        self.assertFalse(self.window.worker.submit("999", request))
        self.enter("5")
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, "5\n")

    def test_invalid_input_and_eof_fail_cleanly(self):
        for end in (False, True):
            with self.subTest(eof=end):
                self.window.editor.setPlainText("var n: int; read n; write n;")
                self.window.start_compile(True)
                self.wait_for(lambda: self.window.input_field.isEnabled())
                if end:
                    self.window.eof_button.click()
                else:
                    self.enter("invalid")
                self.wait_for(lambda: not self.window.busy)
                self.assertIn("no more input" if end else "invalid integer", self.window.runtime_session.runtime_error)
                self.assertIn("failed", self.window.runtime_status.text())
                self.assertFalse(self.window.eof_button.isEnabled())

    def test_edit_debounces_and_refreshes_all_real_stage_results_without_running(self):
        editor = self.window.editor
        editor.setPlainText("")
        editor.setFocus()
        QTest.keyClicks(editor, "write 42;")
        self.assertTrue(editor.document().isModified())
        QTest.qWait(120)
        self.app.processEvents()
        self.assertIsNone(self.window.session)
        self.wait_for(lambda: self.window.session is not None and self.window.session.result and self.window.session.result.ok)
        session = self.window.session
        self.assertEqual(session.source, "write 42;")
        self.assertEqual(session.revision, editor.revision)
        self.assertEqual(session.statuses["execution"], "not run")
        self.assertEqual(self.window.inspectors.tokens.rowCount(), len(session.result.tokens))
        self.assertEqual(self.window.inspectors.ast.topLevelItem(0).text(0), "Program")
        self.assertIsNotNone(session.cfg)
        self.assertIsNotNone(session.complexity)
        self.assertIn("compiled successfully", self.window.compile_status.text())
        self.assertIsNone(self.window.runtime_session)
        self.assertEqual(self.window.terminal.toPlainText(), "")

    def test_run_reuses_current_successful_compilation(self):
        compilation = self.compiled('write "cached";')
        with patch("tiny_compiler.ide.worker.compile_source", side_effect=AssertionError("Unexpected recompilation")) as compiler:
            self.window.start_compile(True)
            self.wait_for(lambda: not self.window.busy)
            compiler.assert_not_called()
        self.assertTrue(self.window.worker.reused_compilation)
        self.assertEqual(self.window.runtime_session.run_id, compilation.run_id)
        self.assertEqual(self.window.runtime_session.output, "cached\n")

    def test_syntax_error_cannot_execute_stale_previously_compiled_code(self):
        self.compiled('write "old output";')
        self.window.start_compile(True)
        self.wait_for(lambda: not self.window.busy)
        self.window.editor.setPlainText("write 99")
        with patch("tiny_compiler.ide.worker.VM", side_effect=AssertionError("Invalid source must not execute")) as vm:
            self.window.start_compile(True)
            self.wait_for(lambda: not self.window.busy)
            vm.assert_not_called()
        self.assertFalse(self.window.session.result.ok)
        self.assertEqual(self.window.session.source, "write 99")
        self.assertEqual(self.window.terminal.toPlainText().count("old output\n"), 1)
        self.assertIn("compilation failed", self.window.compile_status.text())

    def test_stage_navigation_preserves_terminal_and_does_not_compile_or_run(self):
        self.window.editor.setPlainText("var n: int; read n; write n + 1;")
        self.window.start_compile(True)
        self.enter("9")
        self.wait_for(lambda: not self.window.busy)
        transcript = self.window.terminal.toPlainText()
        execution_id = self.window.runtime_session.execution_id
        with patch("tiny_compiler.ide.worker.compile_source") as compiler, patch("tiny_compiler.ide.worker.VM") as vm:
            for index in range(self.window.stage_list.count()):
                self.window.stage_list.setCurrentRow(index)
                self.app.processEvents()
                self.assertEqual(self.window.terminal.toPlainText(), transcript)
            compiler.assert_not_called()
            vm.assert_not_called()
        self.assertEqual(self.window.runtime_session.execution_id, execution_id)

    def test_rapid_edits_and_late_results_cannot_replace_latest_revision(self):
        old = deepcopy(self.compiled("write 1;"))
        for n in range(2, 12):
            self.window.editor.setPlainText("write %d;" % n)
            QTest.qWait(15)
        self.wait_for(lambda: self.window.session.source == "write 11;" and self.window.session.result.ok)
        revision = self.window.session.revision
        self.window.receive_auto_snapshot(old)
        self.window.receive_auto_completed(old)
        self.assertEqual(self.window.session.source, "write 11;")
        self.assertEqual(self.window.session.revision, revision)
        self.assertEqual(self.window.inspectors.source.toPlainText(), "write 11;")

    def test_gui_stays_responsive_during_compilation_and_input_wait(self):
        import tiny_compiler.ide.editor_analysis as service
        actual = service.compile_source
        reached, release = Event(), Event()
        def paused(source, callback):
            reached.set()
            release.wait(5)
            return actual(source, callback)
        ticks = []
        timer = QTimer()
        timer.setInterval(15)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        try:
            with patch.object(service, "compile_source", paused):
                self.window.editor.setPlainText("write 1;")
                self.wait_for(reached.is_set)
                self.window.navigate_to("pipeline")
                QTest.qWait(80)
                self.assertGreater(len(ticks), 2)
                self.window.editor.setPlainText("write 2;")
                release.set()
                self.wait_for(lambda: self.window.session is not None and self.window.session.source == "write 2;" and self.window.session.result.ok)
            self.window.editor.setPlainText("var n: int; read n;")
            self.window.start_compile(True)
            self.wait_for(lambda: self.window.input_field.isEnabled())
            count = len(ticks)
            QTest.qWait(80)
            self.assertGreater(len(ticks), count)
        finally:
            release.set()
            timer.stop()

    def test_compiling_new_source_while_old_runtime_waits_preserves_both_identities(self):
        original = "var n: int; read n; write n + 1;"
        self.window.editor.setPlainText(original)
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.pending_input is not None)
        request = self.window.pending_input
        new_source = 'write "new version";'
        compilation = self.compiled(new_source)
        self.assertEqual(self.window.pending_input, request)
        self.assertEqual(self.window.runtime_session.source, original)
        self.assertEqual(self.window.inspectors.source.toPlainText(), new_source)
        self.window.navigate_to("execution")
        self.assertTrue(self.window.stale_banner.isVisible())
        self.assertIn("Earlier runtime source", self.window.inspectors.execution.toPlainText())
        self.enter("41")
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, "42\n")
        self.assertEqual(self.window.session.run_id, compilation.run_id)
        self.assertEqual(self.window.session.source, new_source)
        self.assertIn("AVAILABLE", self.window.stage_list.item(10).text())
        self.window.navigate_to("source")
        self.assertFalse(self.window.stale_banner.isVisible())

    def test_waiting_run_explains_unsupported_action_and_clear_keeps_input_alive(self):
        self.window.editor.setPlainText("var n: int; read n; write n;")
        self.window.start_compile(True)
        self.wait_for(lambda: self.window.pending_input is not None)
        request = self.window.pending_input
        self.window.actions["run"].trigger()
        self.assertIn("choose End Input, or Stop", self.window.terminal.toPlainText())
        self.assertEqual(self.window.pending_input, request)
        self.window.actions["clear"].trigger()
        self.assertEqual(self.window.terminal.toPlainText(), "read n> ")
        self.assertTrue(self.window.input_field.isEnabled())
        self.enter("12")
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, "12\n")

    def test_terminal_distinguishes_output_prompt_input_errors_and_status(self):
        self.window.editor.setPlainText('var n: int; write "hello"; read n; write n;')
        self.window.start_compile(True)
        self.enter("oops")
        self.wait_for(lambda: not self.window.busy)
        document = self.window.terminal.document()
        colors = set()
        block = document.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    colors.add(fragment.charFormat().foreground().color().name())
                it += 1
            block = block.next()
        self.assertTrue(set(COLORS[k] for k in ("output", "prompt", "input", "error", "status")) <= colors)

    def test_complete_example_uses_only_in_app_enter_for_every_input(self):
        from tiny_compiler.program_library import load_library
        example = next(e for e in load_library() if e.id == "multi_step")
        self.window.editor.setPlainText(example.source)
        self.window.start_compile(True)
        for value in ("1000", "5", "3"):
            self.enter(value)
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.runtime_session.output, example.expected_output)
        self.assertEqual(self.window.runtime_session.inputs, ["1000", "5", "3"])
