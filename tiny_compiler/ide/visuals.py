"""Native Qt visualizations; every node and trace row uses retained compiler data."""
import math

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QAbstractItemView, QGraphicsItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .session import STAGES

COLORS = {"completed": "#245c53", "active": "#285f8a", "waiting": "#765720",
          "error": "#7d323f", "partial": "#765720", "blocked": "#363e4a",
          "pending": "#25374e", "cancelled": "#5c4454"}


class GraphCanvas(QGraphicsView):
    selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.scene().selectionChanged.connect(self.selection_changed)
        self.setMinimumHeight(180)
        self._fitted = False

    def selection_changed(self):
        selected = self.scene().selectedItems()
        if selected:
            self.selected.emit(selected[0].data(0))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def zoom(self, factor):
        scale = self.transform().m11() * factor
        if 0.15 <= scale <= 3:
            self.scale(factor, factor)

    def fit(self):
        if not self.scene().itemsBoundingRect().isEmpty():
            self.fitInView(self.scene().itemsBoundingRect().adjusted(-15, -15, 15, 15),
                           Qt.AspectRatioMode.KeepAspectRatio)
            self._fitted = True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            QTimer.singleShot(0, self.fit)

    def draw_graph(self, nodes, edges):
        self.scene().clear()
        boxes = {n["id"]: n for n in nodes}
        for source, target, label in edges:
            a, b = boxes[source], boxes[target]
            if b["y"] == a["y"] and b["x"] != a["x"]:
                forward = b["x"] > a["x"]
                start = QPointF(a["x"] + (a["w"] if forward else 0), a["y"] + a["h"] / 2)
                end = QPointF(b["x"] + (0 if forward else b["w"]), b["y"] + b["h"] / 2)
                path = QPainterPath(start)
                path.lineTo(end)
                label_at = (start + end) / 2
                direction = 0 if forward else math.pi
            elif b["y"] > a["y"]:
                start = QPointF(a["x"] + a["w"] / 2, a["y"] + a["h"])
                end = QPointF(b["x"] + b["w"] / 2, b["y"])
                path = QPainterPath(start)
                # Keep skipping edges outside intervening blocks.
                if b["y"] - (a["y"] + a["h"]) > 90:
                    side = max(a["x"] + a["w"], b["x"] + b["w"]) + 45 + source * 8
                    path.lineTo(start.x(), start.y() + 15)
                    path.lineTo(side, start.y() + 15)
                    path.lineTo(side, end.y() - 15)
                    path.lineTo(end.x(), end.y() - 15)
                path.lineTo(end)
                label_at = QPointF(start.x() + 8, start.y() + 12)
                direction = math.pi / 2
            else:
                start = QPointF(a["x"], a["y"] + a["h"] / 2)
                end = QPointF(b["x"], b["y"] + b["h"] / 2)
                side = min(a["x"], b["x"]) - 45 - source * 8
                path = QPainterPath(start)
                path.lineTo(side, start.y())
                path.lineTo(side, end.y())
                path.lineTo(end)
                label_at = QPointF(side, (start.y() + end.y()) / 2)
                direction = 0
            self.scene().addPath(path, QPen(QColor("#7fa7c7"), 2))
            arrow = QPolygonF([end,
                end - QPointF(math.cos(direction - 0.5) * 10, math.sin(direction - 0.5) * 10),
                end - QPointF(math.cos(direction + 0.5) * 10, math.sin(direction + 0.5) * 10)])
            self.scene().addPolygon(arrow, QPen(QColor("#7fa7c7")), QColor("#7fa7c7"))
            if label:
                text = self.scene().addText(label, QFont("Segoe UI", 9))
                text.setDefaultTextColor(QColor("#a9d9e9"))
                text.setPos(label_at)
        for n in nodes:
            item = self.scene().addRect(n["x"], n["y"], n["w"], n["h"],
                                       QPen(QColor("#668aa7")), QColor(COLORS.get(n.get("status"), "#25374e")))
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            item.setData(0, n["id"])
            item.setToolTip(n.get("tooltip", n["text"]))
            text = self.scene().addText(n["text"], QFont("Consolas", 10))
            text.setDefaultTextColor(QColor("#e5eff7"))
            text.setTextWidth(n["w"] - 20)
            text.setPos(n["x"] + 7, n["y"] + 6)
            text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-25, -25, 25, 25))
        if self.isVisible() and not self._fitted:
            QTimer.singleShot(0, self.fit)


class GraphPanel(QWidget):
    def __init__(self, hint):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(hint)
        label.setWordWrap(True)
        layout.addWidget(label)
        controls = QHBoxLayout()
        self.canvas = GraphCanvas()
        for title, callback in (("Zoom +", lambda: self.canvas.zoom(1.2)),
                                ("Zoom −", lambda: self.canvas.zoom(1 / 1.2)),
                                ("Fit", self.canvas.fit)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.canvas)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.splitter.addWidget(self.details)
        self.splitter.setSizes([420, 130])
        layout.addWidget(self.splitter, 1)


class PipelinePanel(GraphPanel):
    stage_selected = Signal(str)

    def __init__(self):
        super().__init__("Live compiler status for this source snapshot. Click a node to open its stage.")
        self.canvas.selected.connect(self.stage_selected.emit)

    def update_session(self, session):
        positions = {"source": (0, 0), "lexical": (245, 0), "syntax": (490, 0),
                     "semantic": (490, 115), "symbols": (490, 230), "ir": (245, 115),
                     "code": (0, 115), "execution": (0, 230)}
        titles = {"source": "Source code", "lexical": "Lexical analysis", "syntax": "Syntax / AST",
                  "semantic": "Semantic analysis", "symbols": "Symbol table", "ir": "Intermediate code",
                  "code": "Target / VM code", "execution": "Execution / diagnostics"}
        nodes = []
        for key, title in STAGES:
            x, y = positions[key]
            state = session.statuses[key]
            nodes.append(dict(id=key, x=x, y=y, w=205, h=80, status=state,
                              text=titles[key] + "\n" + state.upper()))
        edges = [(a, b, "") for a, b in (("source", "lexical"), ("lexical", "syntax"),
                 ("syntax", "semantic"), ("semantic", "ir"), ("ir", "code"), ("code", "execution"))]
        edges.append(("semantic", "symbols", "produces"))
        self.canvas.draw_graph(nodes, edges)
        self.details.setPlainText("Run %s\n%s" % (session.run_id, "\n".join(
            "%s: %s" % (title, session.statuses[key]) for key, title in STAGES)))


class CFGPanel(GraphPanel):
    def __init__(self):
        super().__init__("Control flow from actual IR basic blocks. Select a block for all instructions. Ctrl+wheel zooms.")
        self.graph = None
        self.canvas.selected.connect(self.select_block)

    def update_graph(self, graph):
        self.graph = graph
        self.canvas._fitted = False
        nodes = []
        if graph is None:
            self.canvas.draw_graph([], [])
            self.details.setPlainText("Compile a valid program to generate its control-flow graph.")
            return
        y = 0
        for block in graph.blocks:
            lines = block.text.splitlines()
            text = "B%d  IR [%d, %d)\n" % (block.id, block.start, block.end)
            text += "\n".join(lines[:7]) + ("\n… select for full block" if len(lines) > 7 else "")
            height = 34 + min(len(lines), 8) * 22
            nodes.append(dict(id=block.id, x=75, y=y, w=520, h=height, text=text,
                              tooltip=block.text,
                              status="completed" if block.reachable else "blocked"))
            y += height + 60
        self.canvas.draw_graph(nodes, [(e.source, e.target, e.label) for e in graph.edges])
        if graph.blocks:
            self.select_block(0)

    def select_block(self, number):
        if self.graph is not None:
            block = self.graph.blocks[number]
            edges = ["B%d --%s--> B%d" % (e.source, e.label, e.target)
                     for e in self.graph.edges if e.source == number]
            self.details.setPlainText("B%d | source lines %s | %s\n%s\n\n%s" % (
                number, ", ".join(map(str, block.source_lines)),
                "reachable from entry" if block.reachable else "unreachable",
                block.text, "\n".join(edges) or "Exit block"))


class TracePanel(QWidget):
    source_selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.entries = []
        self.run_id = None
        self.timer = QTimer(self)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self.step)
        layout = QVBoxLayout(self)
        self.hint = QLabel("Recorded execution history, not a re-execution or debugger. Select a row for post-instruction state.")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        controls = QHBoxLayout()
        for title, callback in (("Replay Step", self.step), ("Replay Continue", self.play),
                                ("Pause Replay", self.timer.stop), ("Reset Replay", self.reset)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Step", "IP", "Next IP", "Instruction", "Line", "Output delta"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(self.select_row)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([320, 230])
        layout.addWidget(splitter)

    def set_entries(self, run_id, entries, truncated=False):
        if self.run_id != run_id:
            self.timer.stop()
            self.table.setRowCount(0)
            self.entries = []
            self.details.clear()
            self.run_id = run_id
        self.hint.setText("Actual VM history: %d recorded instructions%s. Replay controls navigate captured rows only." % (
            len(entries), " (capture capped; program continued)" if truncated else ""))
        old_count = len(self.entries)
        self.entries = list(entries)
        self.table.setRowCount(len(entries))
        for row in range(old_count, len(entries)):
            step = entries[row]
            for column, value in enumerate((step.step, step.pc, step.next_pc, step.instruction,
                                              step.line, repr(step.output))):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        if old_count == 0 and entries:
            self.details.setPlainText("Select an instruction, or use Replay Step to inspect the first recorded state.")

    def select_row(self, row, *args):
        if not 0 <= row < len(self.entries):
            return
        entry = self.entries[row]
        output = "".join(e.output for e in self.entries[:row + 1])
        memory = "\n".join("%s = %r" % item for item in entry.memory.items())
        self.details.setPlainText("Step %d | IP %d -> %d | source line %d\n%s\n%s\n\n"
                                  "Variables and temporaries after instruction\n%s\n\n"
                                  "Stack (bottom to top)\n%r\n\nProgram output through this row\n%s%s" % (
            entry.step, entry.pc, entry.next_pc, entry.line, entry.instruction,
            "FAILED: " + entry.error if entry.error else "Completed instruction",
            memory or "(empty)", entry.stack, output,
            "\nState/output fragment truncated at capture limits." if entry.state_truncated else ""))
        if entry.line:
            self.source_selected.emit(entry.line)

    def step(self):
        row = self.table.currentRow() + 1
        if row < len(self.entries):
            self.table.setCurrentCell(row, 0)
        else:
            self.timer.stop()

    def play(self):
        if self.entries:
            self.timer.start()

    def reset(self):
        self.timer.stop()
        if self.entries:
            self.table.setCurrentCell(0, 0)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
