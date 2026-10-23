"""Source editor with a painted line gutter and Tiny-aware highlighting."""
import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal, QStringListModel, QEvent
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QSyntaxHighlighter, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget, QCompleter, QToolTip

from ..lexer import KEYWORDS, tokenize
from ..completion import HELP, completion_prefix, suggestions, visible_symbols, lexical_state
from .editor_analysis import EditorAnalysis


class TinyHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        # Scan strings/comments before identifiers, so comment markers in strings
        # and keywords within comments cannot override one another.
        self.setCurrentBlockState(0)
        styles = {"keyword": "#c4a4ff", "number": "#f6bf72",
                  "string": "#9bd49f", "comment": "#7a91a8"}
        pattern = re.compile(r'//.*|/\*|"(?:\\.|[^"\\])*"?|\b[0-9]+\b|\b[A-Za-z_][A-Za-z_0-9]*\b')
        pos = 0
        if self.previousBlockState() == 1:
            end = text.find("*/")
            if end < 0:
                self.setFormat(0, len(text), QColor(styles["comment"]))
                self.setCurrentBlockState(1)
                return
            self.setFormat(0, end + 2, QColor(styles["comment"]))
            pos = end + 2
        while pos < len(text):
            match = pattern.search(text, pos)
            if match is None:
                break
            token = match.group()
            start, end = match.span()
            kind = None
            if token == "/*":
                close = text.find("*/", end)
                end = len(text) if close < 0 else close + 2
                kind = "comment"
                if close < 0:
                    self.setCurrentBlockState(1)
            elif token.startswith("//"):
                kind = "comment"
            elif token.startswith('"'):
                kind = "string"
            elif token[0].isdigit():
                kind = "number"
            elif token in KEYWORDS:
                kind = "keyword"
            if kind:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(styles[kind]))
                if kind == "keyword":
                    fmt.setFontWeight(QFont.Weight.DemiBold)
                self.setFormat(start, end - start, fmt)
            pos = end


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    analysis_idle = Signal()
    compilation_started = Signal(int)
    compilation_snapshot = Signal(object)
    compilation_ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sourceEditor")
        self.setFont(QFont("Cascadia Code", 11))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.gutter = LineNumbers(self)
        self.highlighter = TinyHighlighter(self.document())
        self.analysis_result = None
        self.analysis_source = None
        self.analysis_worker = None
        self.revision = 0
        self.analysis_revision = -1
        self.analysis_filename = "<untitled>"
        self._external_revision = -1
        self._analysis_closing = False
        self.diagnostics = []
        self.matching_positions = []
        self.completion_options = {}
        self.templates_enabled = True
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseSensitive)
        self.completer.activated.connect(self.accept_completion)
        self.completion_model = QStringListModel(self)
        self.completer.setModel(self.completion_model)
        self.analysis_timer = QTimer(self)
        self.analysis_timer.setSingleShot(True)
        self.analysis_timer.setInterval(350)
        self.analysis_timer.timeout.connect(self.start_analysis)
        self.textChanged.connect(self.schedule_analysis)
        self.viewport().installEventFilter(self)
        self.blockCountChanged.connect(self.update_gutter_margin)
        self.updateRequest.connect(self.update_gutter)
        self.cursorPositionChanged.connect(self.highlight_line)
        self.update_gutter_margin()
        self.highlight_line()

    def gutter_width(self):
        return 20 + self.fontMetrics().horizontalAdvance("9") * len(str(self.blockCount()))

    def update_gutter_margin(self, *args):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor("#111b29"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QColor("#688098"))
                painter.drawText(0, top, self.gutter.width() - 10, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(number + 1))
            top += height
            block = block.next()
            number += 1

    def highlight_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#1c2a3e"))
        selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        selections = [selection]
        for diagnostic in self.diagnostics:
            block = self.document().findBlockByNumber(diagnostic.line - 1)
            if block.isValid():
                cursor = QTextCursor(block)
                line_text = block.text()
                prefix = line_text[:max(0, diagnostic.col - 1)]
                cursor.setPosition(block.position() + len(prefix.encode("utf-16-le")) // 2)
                if cursor.positionInBlock() < block.length() - 1:
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
                error = QTextEdit.ExtraSelection()
                error.cursor = cursor
                error.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                error.format.setUnderlineColor(QColor("#ff8484" if diagnostic.severity == "error" else "#e6c477"))
                selections.append(error)
        source = self.toPlainText()
        position = self.python_position()
        self.matching_positions = self.find_matching_brackets(source, position)
        for index in self.matching_positions:
            bracket = QTextEdit.ExtraSelection()
            cursor = self.textCursor()
            cursor.setPosition(len(source[:index].encode("utf-16-le")) // 2)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            bracket.cursor = cursor
            bracket.format.setBackground(QColor("#397b87"))
            selections.append(bracket)
        self.setExtraSelections(selections)

    def python_position(self):
        return len(self.toPlainText().encode("utf-16-le")[:self.textCursor().position() * 2].decode("utf-16-le", errors="ignore"))

    @staticmethod
    def find_matching_brackets(source, position):
        offsets = [0]
        for line in source.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        brackets = []
        for token in tokenize(source):
            if token.type in ("(", ")", "{", "}"):
                brackets.append((offsets[token.line - 1] + token.col - 1, token.type))
        pairs, stack = {}, []
        for index, kind in brackets:
            if kind in ("(", "{"):
                stack.append((index, kind))
            elif stack and stack[-1][1] == {")": "(", "}": "{"}[kind]:
                opening, _ = stack.pop()
                pairs[opening] = index
                pairs[index] = opening
        for selected in (position, position - 1):
            if selected in pairs:
                return [selected, pairs[selected]]
        return []

    def schedule_analysis(self):
        self.revision += 1
        self.diagnostics = []
        if self.analysis_worker is not None:
            self.analysis_worker.requestInterruption()
        if not self._analysis_closing:
            self.analysis_timer.start()
        self.highlight_line()

    def start_analysis(self):
        if self._analysis_closing or self.analysis_worker is not None:
            return
        source = self.toPlainText()
        if self.analysis_revision == self.revision or self._external_revision == self.revision:
            return
        worker = EditorAnalysis(source, self, revision=self.revision, filename=self.analysis_filename)
        self.analysis_worker = worker
        worker.ready.connect(self.analysis_ready)
        worker.snapshot.connect(self.forward_snapshot)
        worker.completed.connect(self.forward_completed)
        worker.finished.connect(self.analysis_finished)
        self.compilation_started.emit(self.revision)
        worker.start()

    def analysis_ready(self, source, result):
        worker = self.sender()
        if source == self.toPlainText() and worker and worker.session.revision == self.revision and self._external_revision != self.revision:
            self.analysis_source = source
            self.analysis_revision = self.revision
            self.analysis_result = result
            self.diagnostics = result.diagnostics.sorted() if result else []
            self.highlight_line()

    def forward_snapshot(self, session):
        if session.revision == self.revision and session.source == self.toPlainText() and self._external_revision != self.revision and not self._analysis_closing:
            self.compilation_snapshot.emit(session)

    def forward_completed(self, session):
        if session.revision == self.revision and session.source == self.toPlainText() and self._external_revision != self.revision and not self._analysis_closing:
            self.compilation_ready.emit(session)

    def cancel_for_external(self):
        self._external_revision = self.revision
        self.analysis_timer.stop()
        if self.analysis_worker is not None:
            self.analysis_worker.requestInterruption()

    def accept_external(self, session):
        if session.revision == self.revision and session.source == self.toPlainText() and session.result:
            self.analysis_source = session.source
            self.analysis_revision = session.revision
            self.analysis_result = session.result
            self.diagnostics = session.result.diagnostics.sorted()
            self.highlight_line()

    def analysis_finished(self):
        old = self.analysis_worker
        self.analysis_worker = None
        if old:
            old.deleteLater()
        if self._analysis_closing:
            self.analysis_idle.emit()
        elif self.analysis_revision != self.revision and self._external_revision != self.revision:
            self.analysis_timer.start()

    def stop_analysis(self):
        self._analysis_closing = True
        self.analysis_timer.stop()
        self.completer.popup().hide()
        if self.analysis_worker is not None:
            if self.analysis_worker.isRunning():
                self.analysis_worker.requestInterruption()
            return False
        return True

    def show_completions(self):
        source, position = self.toPlainText(), self.python_position()
        if self.textCursor().hasSelection() or (position < len(source) and (source[position].isalnum() or source[position] == "_")):
            self.completer.popup().hide()
            self.completion_options = {}
            return
        table = self.analysis_result.symbols if self.analysis_result else None
        options = suggestions(source, position, table, self.templates_enabled)
        self.completion_options = {option.label: option for option in options}
        self.completion_model.setStringList(list(self.completion_options))
        if not options:
            self.completer.popup().hide()
            return
        self.completer.setCompletionPrefix("")
        self.completer.popup().setCurrentIndex(self.completion_model.index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(320, self.completer.popup().sizeHintForColumn(0) + 28))
        self.completer.complete(rect)

    def accept_completion(self, label):
        option = self.completion_options.get(label)
        if option is None:
            return
        cursor = self.textCursor()
        prefix = completion_prefix(self.toPlainText(), self.python_position())
        # Replace only the typed prefix; selection/surrounding code is preserved.
        if cursor.hasSelection():
            self.completer.popup().hide()
            return
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        indent = re.match(r"[ \t]*", cursor.block().text()).group()
        text = option.text.replace("\n", "\n" + indent)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    def hover_text(self, position):
        cursor = self.textCursor()
        cursor.setPosition(position)
        line = cursor.blockNumber() + 1
        for diagnostic in self.diagnostics:
            if diagnostic.line == line:
                return diagnostic.label() + ": " + diagnostic.message
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText()
        if word in HELP:
            return HELP[word]
        table = self.analysis_result.symbols if self.analysis_result else None
        at = len(self.toPlainText().encode("utf-16-le")[:position * 2].decode("utf-16-le", errors="ignore"))
        for symbol in visible_symbols(self.toPlainText(), at + len(word), table):
            if symbol.name == word:
                return "%s: %s | scope depth %d | storage %s | declared %d:%d" % (
                    symbol.name, symbol.type, symbol.depth, symbol.unique, symbol.line, symbol.col)
        return ""

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() == QEvent.Type.ToolTip:
            text = self.hover_text(self.cursorForPosition(event.pos()).position())
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.show_completions()
            return
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                index = self.completer.popup().currentIndex()
                self.accept_completion(index.data() or "")
                return
            if event.key() == Qt.Key.Key_Escape:
                self.completer.popup().hide()
                return
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                row = self.completer.popup().currentIndex().row()
                row = (row + (1 if event.key() == Qt.Key.Key_Down else -1)) % self.completion_model.rowCount()
                self.completer.popup().setCurrentIndex(self.completion_model.index(row, 0))
                return
        cursor = self.textCursor()
        source = self.toPlainText()
        position = self.python_position()
        typed = event.text()
        next_char = source[position:position + 1]
        context = lexical_state(source[:position])
        code_context = context == "code"
        if typed and typed in ("(", "{", '"') and code_context:
            closing = {"(": ")", "{": "}", '"': '"'}[typed]
            selected = cursor.selectedText().replace("\u2029", "\n")
            cursor.beginEditBlock()
            cursor.insertText(typed + selected + closing)
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
        elif typed and typed in (")", "}", '"') and typed == next_char and (code_context or (typed == '"' and context == "string")):
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            self.setTextCursor(cursor)
        elif event.key() == Qt.Key.Key_Backspace and not cursor.hasSelection() and position > 0 and source[position - 1:position + 1] in ("()", "{}", '""'):
            cursor.beginEditBlock()
            cursor.deleteChar()
            cursor.deletePreviousChar()
            cursor.endEditBlock()
            self.setTextCursor(cursor)
        elif event.key() == Qt.Key.Key_Tab:
            self.insertPlainText("    ")
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.textCursor().block().text()
            indent = re.match(r"[ \t]*", text).group()
            before = text[:self.textCursor().positionInBlock()].rstrip()
            cursor.beginEditBlock()
            addition = "\n" + indent + ("    " if before.endswith("{") else "")
            if before.endswith("{") and next_char == "}":
                cursor.insertText(addition + "\n" + indent)
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(indent) + 1)
            else:
                cursor.insertText(addition)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
        else:
            super().keyPressEvent(event)
        if typed and (completion_prefix(self.toPlainText(), self.python_position()) or typed == ":") and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self.show_completions()
        elif event.key() != Qt.Key.Key_Backspace:
            self.completer.popup().hide()

    def go_to(self, line, col=1):
        block = self.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.Right,
                                QTextCursor.MoveMode.MoveAnchor, max(0, min(col - 1, block.length() - 1)))
            self.setTextCursor(cursor)
            self.setFocus()
