import time
import unittest

from tiny_compiler.completion import suggestions, visible_symbols, TEMPLATES
from tiny_compiler.pipeline import compile_source
from tiny_compiler.lexer import KEYWORDS


class CompletionEngineTests(unittest.TestCase):
    def labels(self, source, table=None):
        return [s.label for s in suggestions(source, len(source), table, templates=False)]

    def test_keywords_types_expressions_and_invalid_contexts(self):
        self.assertEqual(self.labels("wh"), ["while"])
        self.assertEqual(set(self.labels("var x: ")), {"int", "bool"})
        self.assertEqual(self.labels("var "), [])
        self.assertEqual(self.labels('write "wh'), [])
        self.assertEqual(self.labels("// wh"), [])
        self.assertEqual(self.labels("/* comment wh"), [])
        self.assertEqual(self.labels("for"), [])
        self.assertEqual(self.labels("["), [])
        self.assertEqual(self.labels("write @ wh"), [])
        self.assertEqual(self.labels("if "), ["("])
        self.assertIn("not", self.labels("write "))
        self.assertNotIn("else", self.labels("while (false) {} "))
        self.assertIn("else", self.labels("if (true) {} "))

    def test_no_unsupported_functions_or_language_constructs(self):
        options = suggestions("", 0)
        for option in options:
            if "[template]" not in option.label:
                self.assertIn(option.label, KEYWORDS)
        self.assertFalse({"for", "print", "input", "return", "sqrt", "len", "function"} & set(self.labels("")))

    def test_real_symbols_respect_declarations_scopes_and_shadowing(self):
        source = "var x: int = 1; { var x: bool = true; var local: int = 2; write local; } write x;"
        table = compile_source(source).symbols
        inside = source.index("write local")
        visible = visible_symbols(source, inside, table)
        self.assertEqual({s.name: s.type for s in visible}, {"x": "bool", "local": "int"})
        outside = visible_symbols(source, len(source), table)
        self.assertEqual([(s.name, s.type) for s in outside], [("x", "int")])
        self.assertEqual(visible_symbols(source, 0, table), [])
        changed = source.replace("var x: int", "var y: int")
        self.assertNotIn("x", [s.name for s in visible_symbols(changed, len(changed), table)])

    def test_partial_write_read_and_own_initializer(self):
        source = "var count: int = 1; write count;"
        table = compile_source(source).symbols
        self.assertIn("count", self.labels("var count: int = 1; read co", table))
        self.assertIn("count", self.labels("var count: int = 1; write co", table))
        self.assertNotIn("count", self.labels("var count: int = co", table))

    def test_templates_follow_parser_grammar(self):
        for template in TEMPLATES.values():
            result = compile_source("var name: int;\n" + template if template.startswith("read") else template)
            self.assertFalse(any(d.phase in ("lexical", "syntax") for d in result.diagnostics.errors), template)


try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from tiny_compiler.ide.window import MainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "Install requirements.txt")
class SmartEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.editor = self.window.editor
        self.editor.setPlainText("")
        self.editor.setFocus()

    def wait_for(self, condition):
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertTrue(condition())
        self.app.processEvents()

    def tearDown(self):
        self.editor.document().setModified(False)
        self.window.close()
        self.wait_for(lambda: not self.window.isVisible())

    def test_automatic_popup_keyboard_accept_escape_and_manual_trigger(self):
        QTest.keyClicks(self.editor, "wh")
        self.assertIn("while", self.editor.completion_options)
        self.assertTrue(self.editor.completer.popup().isVisible())
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(self.editor.toPlainText(), "while")
        self.editor.setPlainText("wr")
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(self.editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(self.editor, Qt.Key.Key_Down)
        self.assertEqual(self.editor.completer.popup().currentIndex().row(), 1)
        QTest.keyClick(self.editor, Qt.Key.Key_Up)
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.assertEqual(self.editor.toPlainText(), "write")
        self.editor.clear()
        QTest.keyClicks(self.editor, "if")
        QTest.keyClick(self.editor, Qt.Key.Key_Escape)
        self.assertFalse(self.editor.completer.popup().isVisible())
        self.assertEqual(self.editor.toPlainText(), "if")

    def test_pairs_indentation_bracket_matching_and_undo_redo(self):
        QTest.keyClicks(self.editor, "{")
        self.assertEqual(self.editor.toPlainText(), "{}")
        self.assertEqual(set(self.editor.matching_positions), {0, 1})
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.assertEqual(self.editor.toPlainText(), "{\n    \n}")
        QTest.keyClick(self.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.toPlainText(), "{}")
        QTest.keyClick(self.editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.toPlainText(), "{\n    \n}")
        self.editor.clear()
        QTest.keyClicks(self.editor, '"hello"')
        self.assertEqual(self.editor.toPlainText(), '"hello"')
        self.editor.clear()
        QTest.keyClicks(self.editor, "(")
        QTest.keyClick(self.editor, Qt.Key.Key_Backspace)
        self.assertEqual(self.editor.toPlainText(), "")
        QTest.keyClicks(self.editor, "[")
        self.assertEqual(self.editor.toPlainText(), "[")  # arrays are unsupported
        self.editor.setPlainText("// ")
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClicks(self.editor, "(")
        self.assertEqual(self.editor.toPlainText(), "// (")
        self.editor.setPlainText("write ")
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClicks(self.editor, "12")
        self.assertFalse(self.editor.completer.popup().isVisible())

    def test_inline_diagnostics_hover_and_symbol_completion_use_compiler(self):
        source = "var count: int = 2;\nwrite count;"
        self.editor.setPlainText(source)
        self.wait_for(lambda: self.editor.analysis_source == source)
        self.assertIn("Declare", self.editor.hover_text(1))
        self.assertIn("count: int", self.editor.hover_text(source.rindex("count")))
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText("\nwrite co")
        self.editor.show_completions()
        self.assertIn("count", self.editor.completion_options)
        invalid = "var x: int = true;"
        self.editor.setPlainText(invalid)
        self.wait_for(lambda: self.editor.analysis_source == invalid)
        self.assertTrue(any(d.phase == "semantic" for d in self.editor.diagnostics))
        self.assertGreater(len(self.editor.extraSelections()), 1)
        self.assertIn("semantic error", self.editor.hover_text(0))
        self.assertEqual(self.window.session.source, invalid)
        self.assertEqual(self.window.session.statuses["semantic"], "error")
        self.assertIsNone(self.window.runtime_session)
        self.assertEqual(self.window.terminal.toPlainText(), "")

    def test_completion_does_not_overwrite_surroundings_or_execute(self):
        self.editor.setPlainText("wh\nwrite 42;")
        cursor = self.editor.textCursor()
        cursor.setPosition(2)
        self.editor.setTextCursor(cursor)
        self.editor.show_completions()
        self.editor.accept_completion("while")
        self.assertEqual(self.editor.toPlainText(), "while\nwrite 42;")
        self.assertIsNone(self.window.session)
        self.assertFalse(self.window.busy)
        self.assertEqual(self.window.terminal.toPlainText(), "")
