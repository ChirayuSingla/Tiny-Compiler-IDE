"""Searchable, categorized program library with explicit load/run/inspect actions."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..program_library import load_library
from .editor import TinyHighlighter


class ProgramLibrary(QWidget):
    requested = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.entries = []
        self.running = False
        layout = QVBoxLayout(self)
        hint = QLabel("Choose an example. Load creates an editable copy; Run uses its documented sample input.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search programs or compiler concepts…")
        layout.addWidget(self.search)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Program", "Kind"])
        self.tree.setColumnWidth(0, 285)
        splitter.addWidget(self.tree)
        right = QSplitter(Qt.Orientation.Vertical)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        right.addWidget(self.details)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.highlighter = TinyHighlighter(self.preview.document())
        right.addWidget(self.preview)
        right.setSizes([200, 300])
        splitter.addWidget(right)
        splitter.setSizes([250, 440])
        layout.addWidget(splitter, 1)
        actions = QHBoxLayout()
        self.buttons = {}
        for key, title in (("load", "Load into Editor"), ("run", "Run Example"),
                           ("inspect", "Inspect Compilation")):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, action=key: self.request(action))
            actions.addWidget(button)
            self.buttons[key] = button
        layout.addLayout(actions)
        try:
            self.entries = load_library()
            for level in ("Beginner", "Intermediate", "Advanced"):
                group = QTreeWidgetItem(self.tree, [level])
                for entry in self.entries:
                    if entry.difficulty == level:
                        item = QTreeWidgetItem(group, [entry.name, "Intentional " + entry.expected_error + " error"
                                                       if entry.expected_error else "Valid program"])
                        item.setData(0, Qt.ItemDataRole.UserRole, entry.id)
                group.setExpanded(True)
            if self.tree.topLevelItemCount():
                self.tree.setCurrentItem(self.tree.topLevelItem(0).child(0))
        except (OSError, ValueError, KeyError) as exc:
            self.details.setPlainText("Program library unavailable: %s" % exc)
        self.tree.currentItemChanged.connect(self.selection_changed)
        self.search.textChanged.connect(self.filter)
        self.selection_changed()

    def selected(self):
        item = self.tree.currentItem()
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        return next((entry for entry in self.entries if entry.id == key), None)

    def selection_changed(self, *args):
        entry = self.selected()
        for key, button in self.buttons.items():
            button.setEnabled(entry is not None and (key == "load" or not self.running))
        if entry is None:
            return
        warning = "\nINTENTIONAL ERROR DEMONSTRATION: expected %s error containing %r.\n" % (
            entry.expected_error, entry.expected_message) if entry.expected_error else ""
        self.details.setPlainText("%s | %s\n%s\nConcepts: %s\n%s\nSample input\n%s\n\nExpected program output\n%s" % (
            entry.name, entry.difficulty, entry.description, ", ".join(entry.concepts), warning,
            entry.sample_input or "(none)", entry.expected_output or "(none)"))
        try:
            self.preview.setPlainText(entry.source)
        except (OSError, UnicodeError) as exc:
            self.preview.setPlainText("Source unavailable: %s" % exc)
            for button in self.buttons.values():
                button.setEnabled(False)

    def request(self, action):
        entry = self.selected()
        if entry is not None and (action == "load" or not self.running):
            self.requested.emit(entry, action)

    def set_running(self, running):
        self.running = running
        self.selection_changed()

    def select_id(self, key):
        for group_index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(group_index)
            for index in range(group.childCount()):
                item = group.child(index)
                if item.data(0, Qt.ItemDataRole.UserRole) == key:
                    self.tree.setCurrentItem(item)
                    self.tree.scrollToItem(group)
                    return

    def filter(self, text):
        needle = text.casefold()
        entries = {entry.id: entry for entry in self.entries}
        for group_index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(group_index)
            visible = False
            for index in range(group.childCount()):
                item = group.child(index)
                entry = entries[item.data(0, Qt.ItemDataRole.UserRole)]
                match = needle in " ".join([entry.name, entry.description, entry.difficulty] + entry.concepts).casefold()
                item.setHidden(not match)
                visible |= match
            group.setHidden(not visible)
