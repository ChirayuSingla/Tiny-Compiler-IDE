import time
import unittest

from tiny_compiler.control_flow import build_cfg
from tiny_compiler.pipeline import compile_source
from tiny_compiler.vm import VM
from tiny_compiler.runtime import InputReader
from tiny_compiler.execution_trace import TRACE_LIMIT
from tiny_compiler.diagnostics import TinyRuntimeError


class FlowAndTraceTests(unittest.TestCase):
    def test_blocks_partition_real_ir_and_branches_are_labelled(self):
        result = compile_source('var x: int = 2; if (x > 0) { write x; } else { write 0; }')
        graph = build_cfg(result.ir)
        indices = [i for b in graph.blocks for i in range(b.start, b.end)]
        self.assertEqual(indices, list(range(len(result.ir))))
        self.assertEqual({e.label for e in graph.edges}, {"true", "false", "jump", "next"})
        self.assertTrue(all(b.reachable for b in graph.blocks))

    def test_loop_cfg_has_real_back_edge(self):
        graph = build_cfg(compile_source("var i: int = 0; while (i < 3) { i = i + 1; }").ir)
        self.assertTrue(any(e.target <= e.source for e in graph.edges))
        self.assertEqual(build_cfg([]).blocks, [])

    def test_short_circuit_cfg_includes_conditional_edges(self):
        graph = build_cfg(compile_source("var a: bool = true; write a and false or a;").ir)
        self.assertGreaterEqual(sum(e.label in ("true", "false") for e in graph.edges), 4)

    def test_trace_records_post_state_ip_output_and_actual_jump(self):
        result = compile_source('var n: int; read n; while (n > 0) { write n; n = n - 1; }')
        entries = []
        machine = VM(result.code, InputReader(["2"]), on_step=entries.append)
        output = machine.run().getvalue()
        self.assertEqual("".join(e.output for e in entries), output)
        self.assertEqual(entries[-1].memory, machine.memory)
        self.assertEqual(len(entries), machine.steps)
        self.assertEqual(entries[-1].instruction, "HALT")
        self.assertTrue(any(e.next_pc < e.pc for e in entries))
        read = next(e for e in entries if e.instruction == "READ_INT n")
        self.assertEqual(read.memory["n"], 2)
        self.assertEqual(read.next_pc, read.pc + 1)

    def test_failed_instruction_is_retained_and_observer_can_stop_capture(self):
        entries = []
        result = compile_source("var z: int = 0; write 1 / z;")
        with self.assertRaises(TinyRuntimeError):
            VM(result.code, on_step=entries.append).run()
        self.assertIn("division by zero", entries[-1].error)
        self.assertEqual(entries[-1].instruction, "DIV")
        captured = []
        def observe(entry):
            captured.append(entry)
            return False
        output = VM(compile_source("write 42;").code, on_step=observe).run().getvalue()
        self.assertEqual(output, "42\n")
        self.assertEqual(len(captured), 1)


try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from tiny_compiler.ide.window import MainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "Install requirements.txt")
class VisualizationWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()

    def wait_for(self, condition):
        deadline = time.monotonic() + 15
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
        self.app.processEvents()

    def test_visualizations_use_retained_data_and_replay_does_not_run_vm(self):
        self.window.editor.setPlainText("var i: int = 0; while (i < 3) { i = i + 1; } write i;")
        self.window.start_compile(True)
        self.wait_for(lambda: not self.window.busy)
        session = self.window.session
        self.assertIsNotNone(session.cfg)
        self.assertEqual(self.window.inspectors.trace.table.rowCount(), session.steps)
        terminal = self.window.terminal.toPlainText()
        for index in range(self.window.stage_list.count()):
            self.window.stage_list.setCurrentRow(index)
            self.assertEqual(self.window.stack.currentIndex(), index)
            self.assertEqual(self.window.session.run_id, session.run_id)
            self.assertEqual(self.window.terminal.toPlainText(), terminal)
        self.window.inspectors.trace.step()
        self.window.inspectors.trace.reset()
        self.assertFalse(self.window.busy)
        self.assertEqual(self.window.terminal.toPlainText(), terminal)
        self.window.inspectors.pipeline.stage_selected.emit("syntax")
        self.assertEqual(self.window.stage_list.currentRow(), 2)

    def test_search_filters_actual_symbol_rows(self):
        self.window.editor.setPlainText("var apple: int = 1; var pear: bool = true; write apple, pear;")
        self.window.start_compile()
        self.wait_for(lambda: not self.window.busy)
        views = self.window.inspectors
        views.symbol_search.setText("pear")
        self.assertTrue(views.symbols.isRowHidden(0))
        self.assertFalse(views.symbols.isRowHidden(1))
        views.symbol_search.clear()
        self.assertFalse(views.symbols.isRowHidden(0))

    def test_pipeline_highlights_failure_and_trace_capture_is_bounded(self):
        self.window.editor.setPlainText("write missing;")
        self.window.start_compile()
        self.wait_for(lambda: not self.window.busy)
        self.assertIn("Semantic Analysis: error", self.window.inspectors.pipeline.details.toPlainText())
        self.assertIsNone(self.window.session.cfg)
        self.window.editor.setPlainText("var i: int = 0; while (i < 500) { i = i + 1; } write i;")
        self.window.start_compile(True)
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(len(self.window.session.trace), TRACE_LIMIT)
        self.assertTrue(self.window.session.trace_truncated)
        self.assertEqual(self.window.session.output, "500\n")

    def test_complexity_and_graph_remain_bound_to_snapshot_after_edits(self):
        source = "var n: int; read n; var i: int = 0; while (i < n) { i = i + 1; } write i;"
        self.window.editor.setPlainText(source)
        self.window.start_compile(True, "3")
        self.wait_for(lambda: not self.window.busy)
        session = self.window.session
        self.assertEqual(session.complexity.time, "O(n)")
        self.window.navigate_to("complexity")
        text = self.window.inspectors.complexity.toPlainText()
        self.assertIn("Estimated asymptotic time: O(n)", text)
        self.assertIn("Measured runtime is separate", text)
        terminal = self.window.terminal.toPlainText()
        self.window.editor.setPlainText("write 42;")
        self.assertTrue(self.window.stale_banner.isVisible())
        self.assertEqual(self.window.inspectors.complexity.toPlainText(), text)
        self.assertEqual(self.window.session.run_id, session.run_id)
        for key in ("cfg", "pipeline", "trace", "complexity"):
            self.window.navigate_to(key)
            self.assertEqual(self.window.terminal.toPlainText(), terminal)
        self.window.start_compile(False)
        self.wait_for(lambda: not self.window.busy)
        self.assertEqual(self.window.session.complexity.time, "O(1)")
        self.assertEqual(self.window.inspectors.trace.table.rowCount(), len(session.trace))
        self.assertEqual(self.window.runtime_session.execution_id, session.execution_id)
        self.assertIn("Earlier runtime source", self.window.inspectors.execution.toPlainText())
