"""Persistent rich-text terminal; all program text is inserted as literal text."""
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

COLORS = {"output": "#d8e4f2", "prompt": "#6bddd0", "input": "#ffcf85",
          "error": "#ff9eaa", "status": "#9ed5ad", "hint": "#9ab4cf"}


class Terminal(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setFont(QFont("Cascadia Code", 10))

    def write(self, text, role="output"):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(COLORS[role]))
        fmt.setFont(self.font())
        cursor.insertText(text, fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
