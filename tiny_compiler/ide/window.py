"""Desktop IDE layout, file actions, stage navigation and asynchronous I/O."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QTextCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
                               QStackedWidget, QToolBar, QVBoxLayout, QWidget)

from .editor import CodeEditor
from .session import STAGES, NAVIGATION
from .session import RunSession
from .views import Inspectors
from .worker import CompilerWorker
from .terminal import Terminal

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = '''// Tiny playground - edit, compile, explore\nvar n: int = 5;\nvar total: int = 0;\nwhile (n > 0) {\n    total = total + n;\n    n = n - 1;\n}\nwrite "Sum =", total;\n'''

STYLE = """
QMainWindow, QWidget { background: #111b29; color: #d8e4f2; font-family: 'Segoe UI'; font-size: 10pt; }
QToolBar { background: #182639; border: 0; spacing: 8px; padding: 9px; }
QToolButton, QPushButton { background: #25374e; border: 1px solid #354a63; border-radius: 5px; padding: 7px 13px; }
QToolButton:hover, QPushButton:hover { background: #354d69; }
QToolButton:checked { background: #26645d; border: 1px solid #6bddd0; }
QToolButton:disabled, QPushButton:disabled { color: #61738a; background: #1b283a; }
QPlainTextEdit, QTextEdit, QTreeWidget, QTableWidget, QListWidget { background: #142032; border: 1px solid #2a3b50; selection-background-color: #325d84; alternate-background-color: #18273a; }
QPlainTextEdit, QTextEdit { padding: 9px; font-family: 'Cascadia Code', Consolas, monospace; }
QListWidget { outline: none; }
QListWidget { font-size: 9pt; }
QListWidget::item { padding: 6px 7px; border-bottom: 1px solid #223248; }
QListWidget::item:selected { background: #244c6d; border-left: 3px solid #62dbce; }
QHeaderView::section { background: #25374e; color: #b7cee2; padding: 7px; border: 0; }
QLineEdit, QComboBox { background: #182a3e; border: 1px solid #3b536e; border-radius: 4px; padding: 7px; }
QSplitter::handle { background: #26374b; }
QStatusBar { background: #182639; color: #9db4cc; }
QLabel#eyebrow { color: #6bddd0; font-size: 9pt; font-weight: 600; }
QLabel#stageTitle { font-size: 16pt; font-weight: 600; }
QLabel#staleBanner { background: #543f25; color: #ffe0a0; padding: 7px; border-radius: 4px; }
QLabel#subtle { color: #93aac1; font-size: 9pt; }
"""


def panel(title, content, subtitle=None):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(8, 8, 8, 8)
    label = QLabel(title)
    label.setObjectName("eyebrow")
    layout.addWidget(label)
    if subtitle:
        hint = QLabel(subtitle)
        hint.setObjectName("subtle")
        layout.addWidget(hint)
    layout.addWidget(content, 1)
    return widget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.path = None
        self.session = None
        self.runtime_session = None
        self.pending_input = None
        self._announced_execution = None
        self.worker = None
        self.busy = False
        self._closing = False
        self._close_approved = False
        self._last_statuses = {}
        self._sample_input = None
        self.resize(1500, 960)
        self.setMinimumSize(1000, 680)
        self.setStyleSheet(STYLE)
        self.editor = CodeEditor()
        self.editor.analysis_idle.connect(self.editor_idle)
        self.editor.setPlainText(SAMPLE)
        self.editor.document().setModified(False)
        self.stage_list = QListWidget()
        self.stage_list.setObjectName("stageNavigation")
        self.stage_list.setMinimumWidth(235)
        for i, (_, title) in enumerate(NAVIGATION):
            QListWidgetItem("%02d  %s\npending" % (i + 1, title), self.stage_list)
        self.stack = QStackedWidget()
        self.inspectors = Inspectors(self.stack)
        self.stage_title = QLabel(STAGES[0][1])
        self.stage_title.setObjectName("stageTitle")
        self.stage_hint = QLabel("Compile once. Explore every stage.")
        self.stage_hint.setObjectName("subtle")
        self.stale_banner = QLabel("Source changed — these results belong to the last compiled snapshot. Recompile to update.")
        self.stale_banner.setObjectName("staleBanner")
        self.stale_banner.setWordWrap(True)
        self.stale_banner.hide()
        inspection = QWidget()
        layout = QVBoxLayout(inspection)
        layout.addWidget(self.stage_title)
        layout.addWidget(self.stage_hint)
        layout.addWidget(self.stale_banner)
        layout.addWidget(self.stack, 1)
        self.horizontal = QSplitter(Qt.Orientation.Horizontal)
        self.horizontal.addWidget(panel("SOURCE EDITOR", self.editor, "Tiny  •  UTF-8  •  Ctrl+Enter to run"))
        self.horizontal.addWidget(inspection)
        self.horizontal.addWidget(panel("COMPILER STAGES", self.stage_list, "Select a stage to inspect"))
        self.horizontal.setSizes([520, 650, 280])
        self.horizontal.setCollapsible(0, False)
        self.horizontal.setCollapsible(1, False)
        self.horizontal.setCollapsible(2, False)
        self.terminal = Terminal()
        self.terminal.setObjectName("terminalOutput")
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Cascadia Code", 10))
        self.terminal.setPlaceholderText("Program output, input prompts and diagnostics will appear here.")
        terminal_panel = panel("TERMINAL", self.terminal)
        status_row = QHBoxLayout()
        self.compile_status = QLabel("Compilation: scheduled")
        self.runtime_status = QLabel("Runtime: idle")
        status_row.addWidget(self.compile_status, 1)
        status_row.addWidget(self.runtime_status, 1)
        terminal_panel.layout().insertLayout(1, status_row)
        input_row = QHBoxLayout()
        self.input_label = QLabel("stdin ›")
        self.input_field = QLineEdit()
        self.input_field.setObjectName("terminalInput")
        self.input_field.setPlaceholderText("Input becomes available when a read statement is waiting")
        self.input_field.setEnabled(False)
        self.send_button = QPushButton("Send input")
        self.send_button.setEnabled(False)
        self.eof_button = QPushButton("End Input")
        self.eof_button.setEnabled(False)
        self.eof_button.setToolTip("Send end-of-input to the waiting read statement")
        input_row.addWidget(self.input_label)
        input_row.addWidget(self.input_field, 1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.eof_button)
        terminal_panel.layout().addLayout(input_row)
        self.vertical = QSplitter(Qt.Orientation.Vertical)
        self.vertical.addWidget(self.horizontal)
        self.vertical.addWidget(terminal_panel)
        self.vertical.setSizes([650, 240])
        self.vertical.setCollapsible(0, False)
        self.vertical.setCollapsible(1, False)
        self.setCentralWidget(self.vertical)
        self.build_toolbar()
        self.stage_list.currentRowChanged.connect(self.select_stage)
        self.stage_list.setCurrentRow(0)
        self.editor.textChanged.connect(self.source_changed)
        self.editor.cursorPositionChanged.connect(self.cursor_status)
        self.send_button.clicked.connect(self.send_input)
        self.input_field.returnPressed.connect(self.send_input)
        self.eof_button.clicked.connect(self.end_input)
        self.editor.compilation_started.connect(self.auto_started)
        self.editor.compilation_snapshot.connect(self.receive_auto_snapshot)
        self.editor.compilation_ready.connect(self.receive_auto_completed)
        self.inspectors.tokens.cellDoubleClicked.connect(self.token_selected)
        self.inspectors.symbols.cellDoubleClicked.connect(self.symbol_selected)
        self.inspectors.ast.itemDoubleClicked.connect(self.ast_selected)
        self.inspectors.pipeline.stage_selected.connect(self.navigate_to)
        self.inspectors.trace.source_selected.connect(self.trace_source)
        self.inspectors.library.requested.connect(self.library_action)
        self.statusBar().showMessage("Ready — write a program, then Compile or Run")
        self.update_title()

    def build_toolbar(self):
        toolbar = QToolBar("Main toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.actions = {}
        for key, title, shortcut, handler in (
                ("new", "New", "Ctrl+N", self.new_file),
                ("open", "Open", "Ctrl+O", self.open_file),
                ("save", "Save", "Ctrl+S", self.save_file),
                ("compile", "Compile", "F5", lambda: self.start_compile(False)),
                ("run", "Run", "Ctrl+Return", lambda: self.start_compile(True)),
                ("stop", "Stop", "Shift+F5", self.stop),
                ("clear", "Clear Terminal", "Ctrl+L", self.clear_output)):
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)
            toolbar.addAction(action)
            self.actions[key] = action
        self.actions["stop"].setEnabled(False)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Sample  "))
        self.samples = QComboBox()
        self.samples.addItem("Choose a program…", None)
        for path in sorted((ROOT / "examples").glob("*.tiny")):
            self.samples.addItem(path.stem.replace("_", " "), path)
        toolbar.addWidget(self.samples)
        self.samples.activated.connect(self.load_sample)
        library_action = QAction("Program Library", self)
        library_action.triggered.connect(lambda: self.navigate_to("library"))
        toolbar.addAction(library_action)
        self.demo_action = QAction("Demo Mode", self)
        self.demo_action.setCheckable(True)
        self.demo_action.setToolTip("Show the live pipeline when compiling; use trace replay for presentation.")
        toolbar.addAction(self.demo_action)
        save_as = QAction("Save As…", self)
        save_as.setShortcut("Ctrl+Shift+S")
        save_as.triggered.connect(self.save_as)
        menu = self.menuBar().addMenu("File")
        for key in ("new", "open", "save"):
            menu.addAction(self.actions[key])
        menu.addAction(save_as)

    def update_title(self):
        self.editor.analysis_filename = str(self.path) if self.path else "<untitled>"
        name = self.path.name if self.path else "Untitled.tiny"
        self.setWindowTitle("%s%s — Tiny Compiler IDE" % (
            "*" if self.editor.document().isModified() else "", name))

    def source_changed(self):
        self.compile_status.setText("Compilation: modified — scheduled in 350 ms")
        self.update_title()
        self.update_stale()

    def update_stale(self):
        key = NAVIGATION[self.stage_list.currentRow()][0] if self.stage_list.currentRow() >= 0 else "source"
        inspected = self.runtime_session if key in ("execution", "trace") and self.runtime_session else self.session
        stale = inspected is not None and inspected.stale(self.editor.toPlainText())
        self.stale_banner.setVisible(stale)
        self.stale_banner.setText("This runtime uses an earlier source version. Compilation views follow the editor; input still belongs to the running program."
                                 if key in ("execution", "trace") else
                                 "Source changed — compilation is scheduled. These results belong to the preceding snapshot.")
        self.stage_hint.setText("%s %s  •  revision %d  •  %s" % (
            "Execution" if key in ("execution", "trace") and inspected and inspected.execution_id else "Compilation",
            (inspected.execution_id or inspected.run_id) if key in ("execution", "trace") else inspected.run_id,
            inspected.revision, "Earlier source version" if stale else "Matches editor contents")
            if inspected else "Edit source to compile automatically; Run executes explicitly.")

    def cursor_status(self):
        cursor = self.editor.textCursor()
        self.statusBar().showMessage("Line %d, column %d%s" % (
            cursor.blockNumber() + 1, cursor.positionInBlock() + 1,
            "  •  Working in background" if self.busy else ""))

    def select_stage(self, index):
        if 0 <= index < len(NAVIGATION):
            self.stack.setCurrentIndex(index)
            self.stage_title.setText(NAVIGATION[index][1])
            self.update_stale()

    def navigate_to(self, key):
        for index, (name, _) in enumerate(NAVIGATION):
            if name == key:
                self.stage_list.setCurrentRow(index)
                return

    def trace_source(self, line):
        if self.runtime_session and not self.runtime_session.stale(self.editor.toPlainText()):
            self.editor.go_to(line)

    def receive_trace(self, payload):
        execution_id, entries = payload
        runtime = self.runtime_session
        if runtime and runtime.execution_id == execution_id:
            last = runtime.trace[-1].step if runtime.trace else 0
            runtime.trace.extend(entry for entry in entries if entry.step > last)
            self.inspectors.trace.set_entries(execution_id, runtime.trace, runtime.trace_truncated)

    def append_terminal(self, text, role="output"):
        self.terminal.write(text, role)

    def append_diagnostic(self, text):
        if self.terminal.toPlainText() and not self.terminal.toPlainText().endswith("\n"):
            self.append_terminal("\n")
        self.append_terminal(text + "\n", "error")

    def terminal_status(self, text, role="status"):
        if self.terminal.toPlainText() and not self.terminal.toPlainText().endswith("\n"):
            self.append_terminal("\n")
        self.append_terminal("[" + text + "]\n", role)

    def clear_output(self):
        self.terminal.clear()
        if self.pending_input:
            self.append_terminal("read %s> " % self.pending_input.name, "prompt")

    def set_busy(self, busy):
        self.busy = busy
        for key in ("compile", "run"):
            self.actions[key].setEnabled(not busy)
        # A second Run explains how to finish/cancel the current program rather
        # than silently ignoring the user's action while stdin is waiting.
        self.actions["run"].setEnabled(True)
        self.actions["stop"].setEnabled(busy)
        self.inspectors.library.set_running(busy)
        if not busy:
            self.input_field.setEnabled(False)
            self.send_button.setEnabled(False)
            self.eof_button.setEnabled(False)

    def start_compile(self, execute=False, sample_input=None):
        if self.busy or (self.worker and self.worker.isRunning()):
            message = "Waiting for input: enter a value, choose End Input, or Stop before starting another program." if self.pending_input else "A program is active. Use Stop before starting another program."
            self.terminal_status(message, "hint")
            self.statusBar().showMessage(message)
            return
        self.set_busy(True)
        self._sample_input = sample_input
        filename = str(self.path) if self.path else "<untitled>"
        source, revision = self.editor.toPlainText(), self.editor.revision
        cached = self.session if execute and self.session and self.session.revision == revision and self.session.source == source and self.session.result and self.session.result.ok and self.session.statuses["code"] == "completed" else None
        self.editor.cancel_for_external()
        self.worker = CompilerWorker(source, filename, execute, parent=self, compiled=cached, revision=revision)
        worker = self.worker
        from copy import deepcopy
        self.session = deepcopy(worker.session)
        if execute:
            self.runtime_session = self.session
            self.runtime_status.setText("Runtime: preparing — revision %d" % revision)
        self.pending_input = None
        self._last_statuses = {}
        self.inspectors.update(self.session, self.runtime_session)
        self.receive_snapshot(self.session)
        self.worker.snapshot.connect(lambda session: self.receive_snapshot(session) if self.worker is worker else None)
        self.worker.output.connect(lambda text: self.append_terminal(text) if self.worker is worker else None)
        self.worker.input_requested.connect(lambda request: self.request_input(request) if self.worker is worker else None)
        self.worker.diagnostic.connect(lambda text: self.append_diagnostic(text) if self.worker is worker else None)
        self.worker.completed.connect(lambda session: self.run_completed(session) if self.worker is worker else None)
        self.worker.trace_ready.connect(lambda payload: self.receive_trace(payload) if self.worker is worker else None)
        self.worker.finished.connect(lambda: self.worker_finished() if self.worker is worker else None)
        self.worker.start()
        if self.demo_action.isChecked():
            self.navigate_to("pipeline")
        self.statusBar().showMessage("Compiling in background…")

    def auto_started(self, revision):
        if revision == self.editor.revision:
            self.compile_status.setText("Compilation: compiling revision %d…" % revision)

    def receive_auto_snapshot(self, session):
        if session.revision == self.editor.revision and session.source == self.editor.toPlainText():
            self.receive_snapshot(session, automatic=True)

    def receive_auto_completed(self, session):
        if session.revision == self.editor.revision and session.source == self.editor.toPlainText():
            self.receive_snapshot(session, automatic=True)

    def refresh_inspection(self):
        if self.session:
            self.inspectors.update(self.session, self.runtime_session)
        self.update_stale()

    def receive_snapshot(self, session, automatic=False):
        if not automatic and session.execution_id:
            self.runtime_session = session
            state = session.statuses["execution"]
            if state == "active" and self._announced_execution != session.execution_id:
                self._announced_execution = session.execution_id
                self.terminal_status("Running program %s — revision %d" % (session.execution_id, session.revision))
                self.runtime_status.setText("Runtime: running %s — revision %d" % (session.execution_id, session.revision))
        current = session.revision == self.editor.revision and session.source == self.editor.toPlainText()
        same = self.session and self.session.run_id == session.run_id and self.session.revision == session.revision
        if not current and not same:
            self.refresh_inspection()
            return
        self.session = session
        if current:
            if session.result and session.result.ok:
                self.compile_status.setText("Compilation: compiled successfully — revision %d" % session.revision)
                if not automatic:
                    self.editor.accept_external(session)
            elif session.result and session.result.diagnostics.has_errors():
                self.compile_status.setText("Compilation: compilation failed — revision %d" % session.revision)
                if not automatic:
                    self.editor.accept_external(session)
            else:
                self.compile_status.setText("Compilation: compiling revision %d…" % session.revision)
        for i, (key, title) in enumerate(STAGES):
            status = self.runtime_session.statuses["execution"] if key == "execution" and self.runtime_session else session.statuses[key]
            item = self.stage_list.item(i)
            item.setText("%02d  %s\n%s" % (i + 1, title, status.upper()))
            item.setForeground(QColor({"completed": "#91dfc3", "active": "#80c8ff",
                                       "error": "#ff9d9d", "waiting": "#ffce80",
                                       "partial": "#ffce80"}.get(status, "#a0b3c9")))
        for i, (key, title) in enumerate(NAVIGATION[len(STAGES):], len(STAGES)):
            trace = self.runtime_session.trace if self.runtime_session else session.trace
            state = "available" if key in ("pipeline", "library") or (key == "cfg" and session.cfg is not None) or (key == "trace" and trace) else "pending"
            if key == "complexity" and session.complexity is not None:
                state = "limited" if session.complexity.time == "Unable to determine" else "estimated"
            self.stage_list.item(i).setText("%02d  %s\n%s" % (i + 1, title, state.upper()))
        self.refresh_inspection()

    def request_input(self, request):
        if not self.busy or not self.worker or self.worker.cancelled.is_set() or request.execution_id != self.worker.session.execution_id:
            return
        name = request.name
        self.pending_input = request
        self.terminal_status("Waiting for input: %s" % name)
        self.append_terminal("read %s> " % name, "prompt")
        self.runtime_status.setText("Runtime: waiting for input (%s) — revision %d" % (name, self.worker.session.revision))
        self.input_label.setText("%s ›" % name)
        self.input_field.setEnabled(True)
        self.input_field.setPlaceholderText("Enter an int or bool value; separate multiple values with spaces")
        self.send_button.setEnabled(True)
        self.eof_button.setEnabled(True)
        self.input_field.setFocus()
        self.statusBar().showMessage("Waiting for input: %s — stage navigation remains available" % name)
        if self._sample_input is not None:
            text = self._sample_input
            self._sample_input = None
            self.input_field.setText(" ".join(text.split()))
            self.send_input()

    def library_action(self, entry, action):
        if action != "load" and self.busy:
            return
        if not self.confirm_discard():
            return
        try:
            source = entry.source
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Cannot load example", str(exc))
            return
        self.path = None
        self.editor.setPlainText(source)
        self.editor.document().setModified(True)
        self.update_title()
        self.statusBar().showMessage("Loaded editable copy: " + entry.name)
        if action in ("run", "inspect"):
            self.start_compile(action == "run", entry.sample_input if entry.sample_input else None)
            if not self.demo_action.isChecked():
                self.navigate_to("execution" if action == "run" else "lexical")

    def send_input(self):
        if self.worker and self.busy and self.input_field.isEnabled() and self.pending_input:
            text = self.input_field.text()
            if not self.worker.submit(text, self.pending_input):
                self.terminal_status("Input request is no longer active; use Run to start a new program.", "hint")
                return
            self.append_terminal(text + "\n", "input")
            self.pending_input = None
            self.input_field.clear()
            self.input_field.setEnabled(False)
            self.send_button.setEnabled(False)
            self.eof_button.setEnabled(False)
            self.runtime_status.setText("Runtime: running — revision %d" % self.worker.session.revision)
            self.statusBar().showMessage("Running in background…")

    def end_input(self):
        if self.worker and self.pending_input and self.worker.submit(None, self.pending_input):
            self.append_terminal("[end of input]\n", "input")
            self.pending_input = None
            self.input_field.setEnabled(False)
            self.send_button.setEnabled(False)
            self.eof_button.setEnabled(False)

    def run_completed(self, session):
        self.receive_snapshot(session)
        self.pending_input = None
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        self.eof_button.setEnabled(False)
        if session.execution_id:
            state = session.statuses["execution"]
            label = "Completed" if state == "completed" else "Stopped" if state == "cancelled" else "Failed"
            self.runtime_status.setText("Runtime: %s — revision %d" % (label.lower(), session.revision))
            self.terminal_status(label + " program " + session.execution_id,
                                 "error" if label == "Failed" else "status")
        state = "Compilation complete" if session.statuses["execution"] == "not run" else "Run finished"
        if session.runtime_error or (session.result and not session.result.ok):
            state = "Finished with diagnostics — select a stage to inspect"
        self.statusBar().showMessage(state)

    def worker_finished(self):
        self.set_busy(False)
        if self._closing:
            QTimer.singleShot(0, self.close)

    def editor_idle(self):
        if self._closing:
            QTimer.singleShot(0, self.close)

    def stop(self):
        if self.worker and self.busy:
            self.worker.cancel()
            self.pending_input = None
            self.input_field.setEnabled(False)
            self.send_button.setEnabled(False)
            self.eof_button.setEnabled(False)
            self.statusBar().showMessage("Stopping… compilation stops between stages; VM stops at the next instruction")

    def confirm_discard(self):
        if not self.editor.document().isModified():
            return True
        answer = QMessageBox.question(self, "Unsaved source", "Save your source changes?",
                                      QMessageBox.StandardButton.Save |
                                      QMessageBox.StandardButton.Discard |
                                      QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_file()
        return answer == QMessageBox.StandardButton.Discard

    def new_file(self):
        if self.confirm_discard():
            self.path = None
            self.editor.clear()
            self.editor.document().setModified(False)
            self.update_title()

    def load_path(self, path):
        try:
            source = Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Cannot open source", str(exc))
            return False
        self.path = Path(path)
        self.editor.setPlainText(source)
        self.editor.document().setModified(False)
        self.update_title()
        return True

    def open_file(self):
        if self.confirm_discard():
            name, _ = QFileDialog.getOpenFileName(self, "Open Tiny source", str(ROOT / "examples"),
                                                 "Tiny source (*.tiny *.tny);;All files (*)")
            if name:
                self.load_path(name)

    def load_sample(self, index):
        path = self.samples.itemData(index)
        if path and self.confirm_discard():
            # Samples are opened as unsaved copies to protect the originals.
            if self.load_path(path):
                self.path = None
                self.editor.document().setModified(True)
                self.update_title()
        self.samples.setCurrentIndex(0)

    def save_file(self):
        if self.path is None:
            return self.save_as()
        try:
            self.path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Cannot save source", str(exc))
            return False
        self.editor.document().setModified(False)
        self.update_title()
        return True

    def save_as(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save Tiny source", str(self.path or ROOT / "untitled.tiny"),
                                             "Tiny source (*.tiny);;All files (*)")
        if not name:
            return False
        previous = self.path
        self.path = Path(name)
        if self.save_file():
            return True
        self.path = previous
        return False

    def token_selected(self, row, column):
        if self.session and self.session.result and not self.session.stale(self.editor.toPlainText()):
            token = self.session.result.tokens[row]
            self.editor.go_to(token.line, token.col)

    def symbol_selected(self, row, column):
        if self.session and self.session.result and not self.session.stale(self.editor.toPlainText()):
            symbol = self.session.result.symbols.all_symbols[row]
            self.editor.go_to(symbol.line, symbol.col)

    def ast_selected(self, item, column):
        location = item.data(0, Qt.ItemDataRole.UserRole)
        if location and self.session and not self.session.stale(self.editor.toPlainText()):
            self.editor.go_to(*location)

    def closeEvent(self, event):
        if self.busy:
            self._closing = True
            self.stop()
            event.ignore()
            return
        if not self._close_approved and not self.confirm_discard():
            self._closing = False
            event.ignore()
            return
        self._close_approved = True
        self._closing = True
        if not self.editor.stop_analysis():
            event.ignore()
            return
        event.accept()
