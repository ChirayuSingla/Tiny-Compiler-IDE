"""Read-only inspectors populated exclusively from a retained RunSession."""
from dataclasses import fields, is_dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QPlainTextEdit, QLineEdit,
                               QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
                               QWidget, QVBoxLayout)

from .. import ast_nodes as A
from ..codegen import format_code
from ..ir import format_ir
from .visuals import PipelinePanel, CFGPanel, TracePanel
from .library import ProgramLibrary


def code_view():
    widget = QPlainTextEdit()
    widget.setReadOnly(True)
    widget.setFont(QFont("Cascadia Code", 10))
    widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return widget


def table_view(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill_table(widget, rows):
    widget.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            widget.setItem(i, j, QTableWidgetItem(str(value)))


def tree_view():
    widget = QTreeWidget()
    widget.setHeaderLabels(["Node / field", "Value / type", "Source"])
    widget.setAlternatingRowColors(True)
    widget.setColumnWidth(0, 235)
    widget.setColumnWidth(1, 150)
    return widget


def fill_ast(widget, node):
    widget.clear()
    if node is None:
        QTreeWidgetItem(widget, ["No AST available", "Compile source to inspect the tree."])
        return

    def walk(parent, value, name=""):
        if isinstance(value, A.Node) and is_dataclass(value):
            detail = getattr(value, "name", getattr(value, "op", getattr(value, "value", "")))
            node_type = getattr(value, "type", None)
            item = QTreeWidgetItem(parent, [
                (name + ": " if name else "") + type(value).__name__,
                str(detail) + (" : " + node_type if node_type else ""),
                "%s:%s" % (value.line, value.col)])
            item.setData(0, Qt.ItemDataRole.UserRole, (value.line, value.col))
            for f in fields(value):
                if f.name not in ("line", "col", "type", "symbol"):
                    v = getattr(value, f.name)
                    if isinstance(v, (A.Node, list)):
                        walk(item, v, f.name)
            symbol = getattr(value, "symbol", None)
            if symbol:
                QTreeWidgetItem(item, ["resolved symbol", symbol.unique + " : " + symbol.type])
        elif isinstance(value, list):
            item = QTreeWidgetItem(parent, [name, "%d items" % len(value)])
            for i, v in enumerate(value):
                walk(item, v, str(i))
    walk(widget, node)
    widget.expandToDepth(3)


def semantic_text(session):
    result = session.result
    status = session.statuses["semantic"]
    if status in ("pending", "blocked", "cancelled") and result.symbols is None:
        return "Semantic analysis has not completed.\nEarlier stage results remain available."
    diags = [d for d in result.diagnostics.sorted() if d.phase == "semantic"]
    text = ["Semantic analysis: " + status,
            "Checks: declarations and scope resolution; int/bool type rules;",
            "assignment compatibility; boolean conditions; constant zero divisors.", ""]
    if result.symbols is not None:
        text.append("Resolved declarations: %d" % len(result.symbols.all_symbols))
    text += ["", "\n\n".join(d.format(session.source, session.filename) for d in diags)
             if diags else "No semantic diagnostics reported."]
    if result.ast is not None:
        text += ["", "Annotated AST (types and resolved symbols):", A.format_ast(result.ast)]
    return "\n".join(text)


class Inspectors:
    def __init__(self, stack):
        self.source = code_view()
        self.tokens = table_view(["#", "Kind", "Lexeme", "Value", "Line", "Column"])
        self.ast = tree_view()
        self.semantic = code_view()
        self.symbols = table_view(["Name", "Type", "Scope", "Storage", "Declared", "Used"])
        self.symbol_search = QLineEdit()
        self.symbol_search.setPlaceholderText("Search name, type, scope or storage…")
        symbols_panel = QWidget()
        symbols_layout = QVBoxLayout(symbols_panel)
        symbols_layout.addWidget(self.symbol_search)
        symbols_layout.addWidget(self.symbols)
        self.symbol_search.textChanged.connect(self.filter_symbols)
        self.ir = code_view()
        self.code = code_view()
        self.execution = code_view()
        self.pipeline = PipelinePanel()
        self.cfg = CFGPanel()
        self.trace = TracePanel()
        self.library = ProgramLibrary()
        self.complexity = code_view()
        self.complexity.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.complexity.setPlainText("Compile a valid program for conservative asymptotic analysis.")
        self._cfg_run = None
        for view in (self.source, self.tokens, self.ast, self.semantic, symbols_panel,
                     self.ir, self.code, self.execution):
            stack.addWidget(view)
        for view in (self.pipeline, self.cfg, self.trace, self.library, self.complexity):
            stack.addWidget(view)
        self.source.setPlainText("Compile or run to capture a source snapshot.\nEdit your program in the editor on the left.")
        self.semantic.setPlainText("Compile to inspect semantic analysis and annotated types.")
        self.ir.setPlainText("No intermediate code yet. Compile a valid program.")
        self.code.setPlainText("No VM code yet. Compile a valid program.")
        self.execution.setPlainText("No execution yet. Run a program to see diagnostics and VM state.")
        fill_ast(self.ast, None)

    def update(self, session, runtime=None):
        self.complexity.setPlainText(session.complexity.text() if session.complexity else
                                    "Complexity analysis is unavailable until compilation completes.\n" + "\n".join(session.enrichment_errors))
        self.pipeline.update_session(session)
        self.update_runtime(session, runtime)
        if self._cfg_run != session.run_id or (self.cfg.graph is None and session.cfg is not None):
            self.cfg.update_graph(session.cfg)
            self._cfg_run = session.run_id
        res = session.result
        self.source.setPlainText(session.source)
        if res is None:
            fill_table(self.tokens, [])
            fill_ast(self.ast, None)
            fill_table(self.symbols, [])
            for view in (self.semantic, self.ir, self.code):
                view.setPlainText("Waiting for this compilation's results…")
            return
        fill_table(self.tokens, [(i, t.type, repr(t.lexeme), repr(t.value), t.line, t.col)
                                 for i, t in enumerate(res.tokens or [])])
        fill_ast(self.ast, res.ast)
        self.semantic.setPlainText(semantic_text(session))
        fill_table(self.symbols, [(s.name, s.type, s.depth, s.unique,
                                  "%d:%d" % (s.line, s.col), "yes" if s.used else "no")
                                 for s in (res.symbols.all_symbols if res.symbols else [])])
        self.filter_symbols(self.symbol_search.text())
        self.symbols.setToolTip("Partial declarations are retained if semantic analysis fails.")
        self.ir.setPlainText(format_ir(res.ir) if res.ir is not None else
                             "Intermediate code unavailable. Complete semantic analysis first.")
        self.code.setPlainText(format_code(res.code) if res.code is not None else
                               "VM code unavailable. Complete intermediate code generation first.")
    def update_runtime(self, compilation, runtime=None):
        session = runtime or compilation
        self.trace.set_entries(session.execution_id or session.run_id, session.trace, session.trace_truncated)
        diagnostics = "\n\n".join(d.format(compilation.source, compilation.filename)
                                    for d in compilation.result.diagnostics.sorted()) if compilation.result else "Compilation in progress."
        memory = "\n".join("  %s = %s" % (k, v) for k, v in session.memory.items())
        association = "Matches current compilation source." if session.source == compilation.source else "Earlier runtime source. Compilation views show the newer editor source."
        self.execution.setPlainText(
            "Current compilation %s | revision %d\nCompilation diagnostics\n%s\n\n"
            "Runtime %s | compiled revision %d | compilation %s\n%s\n"
            "File: %s\nExecution: %s\nVM instructions executed: %d\n\n"
            "Program output\n%s\nRuntime diagnostics\n%s\n\nFinal VM memory\n%s" % (
                compilation.run_id, compilation.revision, diagnostics or "No compiler diagnostics.",
                session.execution_id or "not started", session.revision, session.run_id, association,
                session.filename, session.statuses["execution"], session.steps,
                session.output or "(no output)\n", session.runtime_error or "No runtime errors.", memory or "(empty)"))

    def filter_symbols(self, text):
        needle = text.casefold()
        for row in range(self.symbols.rowCount()):
            self.symbols.setRowHidden(row, not any(needle in self.symbols.item(row, col).text().casefold()
                                                   for col in range(self.symbols.columnCount())))
