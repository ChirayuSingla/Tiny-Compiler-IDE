from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tiny_compiler.program_library import load_library
from tiny_compiler.pipeline import compile_source
from tiny_compiler.vm import VM
from tiny_compiler.ir import interpret_tac
from tiny_compiler.runtime import InputReader, OutputWriter
from tiny_compiler.diagnostics import TinyRuntimeError


class ProgramFixtureTests(unittest.TestCase):
    def test_library_has_three_levels_and_at_least_twenty_real_programs(self):
        entries = load_library()
        self.assertGreaterEqual(len(entries), 20)
        self.assertEqual({e.difficulty for e in entries}, {"Beginner", "Intermediate", "Advanced"})
        self.assertEqual(len({e.id for e in entries}), len(entries))
        for entry in entries:
            self.assertTrue(entry.path.is_file())
            self.assertTrue(entry.description and entry.concepts and entry.source)

    def test_every_valid_example_executes_with_independent_expected_output(self):
        for entry in load_library():
            if entry.expected_error:
                continue
            with self.subTest(example=entry.id):
                result = compile_source(entry.source)
                self.assertTrue(result.ok, repr(result.diagnostics.errors))
                self.assertEqual(VM(result.code, InputReader([entry.sample_input])).run().getvalue(), entry.expected_output)
                self.assertEqual(interpret_tac(result.ir, InputReader([entry.sample_input])).getvalue(), entry.expected_output)

    def test_intentional_error_programs_fail_at_documented_phase(self):
        phases = set()
        for entry in load_library():
            if not entry.expected_error:
                continue
            phases.add(entry.expected_error)
            with self.subTest(example=entry.id):
                result = compile_source(entry.source)
                if entry.expected_error == "runtime":
                    self.assertTrue(result.ok)
                    out = OutputWriter()
                    with self.assertRaises(TinyRuntimeError) as caught:
                        VM(result.code, InputReader([entry.sample_input]), out).run()
                    self.assertIn(entry.expected_message, str(caught.exception))
                    self.assertEqual(out.getvalue(), entry.expected_output)
                else:
                    self.assertFalse(result.ok)
                    self.assertTrue(any(d.phase == entry.expected_error and entry.expected_message in d.message
                                        for d in result.diagnostics.errors), repr(result.diagnostics.errors))
        self.assertEqual(phases, {"lexical", "syntax", "semantic", "runtime"})


try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from tiny_compiler.ide.window import MainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "Install requirements.txt")
class LibraryWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()

    def wait_for(self, condition):
        deadline = time.monotonic() + 12
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertTrue(condition())
        self.app.processEvents()

    def tearDown(self):
        if self.window.busy:
            self.window.stop()
            self.wait_for(lambda: not self.window.busy)
        self.window.editor.document().setModified(False)
        self.window.close()
        self.wait_for(lambda: not self.window.isVisible())

    def test_load_edit_save_creates_copy_and_keeps_original_unchanged(self):
        panel = self.window.inspectors.library
        panel.select_id("sum_n")
        entry = panel.selected()
        original = entry.path.read_bytes()
        panel.buttons["load"].click()
        self.assertEqual(self.window.editor.toPlainText(), entry.source)
        self.assertIsNone(self.window.path)
        self.window.editor.insertPlainText("// editable copy\n")
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "my-program.tiny"
            with patch("tiny_compiler.ide.window.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
                self.assertTrue(self.window.save_file())
            self.assertIn("editable copy", destination.read_text(encoding="utf-8"))
        self.assertEqual(entry.path.read_bytes(), original)

    def test_run_every_library_program_through_real_gui_actions(self):
        panel = self.window.inspectors.library
        for entry in panel.entries:
            with self.subTest(example=entry.id):
                self.window.editor.document().setModified(False)
                panel.select_id(entry.id)
                panel.buttons["run"].click()
                self.wait_for(lambda: not self.window.busy)
                self.assertEqual(self.window.session.source, entry.source)
                self.assertEqual(self.window.session.output, entry.expected_output)
                if entry.expected_error == "runtime":
                    self.assertIn(entry.expected_message, self.window.session.runtime_error)
                elif entry.expected_error:
                    self.assertEqual(self.window.session.statuses[entry.expected_error], "error")
                else:
                    self.assertEqual(self.window.session.statuses["execution"], "completed")

    def test_demo_mode_pipeline_inspect_and_trace_replay_preserve_output(self):
        panel = self.window.inspectors.library
        panel.select_id("sum_n")
        self.window.demo_action.setChecked(True)
        panel.buttons["run"].click()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.stage_list.currentRow(), 8)
        self.assertEqual(self.window.session.output, "15\n")
        output = self.window.terminal.toPlainText()
        run_id = self.window.session.run_id
        self.window.navigate_to("trace")
        self.window.inspectors.trace.step()
        self.window.inspectors.trace.play()
        self.app.processEvents()
        self.window.inspectors.trace.reset()
        self.assertEqual(self.window.session.run_id, run_id)
        self.assertEqual(self.window.terminal.toPlainText(), output)
        self.window.editor.document().setModified(False)
        panel.buttons["inspect"].click()
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.statuses["execution"], "not run")
        self.assertEqual(self.window.terminal.toPlainText(), output)

    def test_library_search_matches_concepts(self):
        panel = self.window.inspectors.library
        panel.search.setText("short circuit")
        visible = [panel.tree.topLevelItem(i).child(j).text(0)
                   for i in range(panel.tree.topLevelItemCount())
                   for j in range(panel.tree.topLevelItem(i).childCount())
                   if not panel.tree.topLevelItem(i).child(j).isHidden()]
        self.assertEqual(visible, ["Prime number checker"])
