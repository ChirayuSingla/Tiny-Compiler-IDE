"""Qt-free run state and cancellable I/O adapters for the actual compiler/VM."""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Event
from time import monotonic
from typing import Optional
from uuid import uuid4

from ..pipeline import CompilationResult
from ..runtime import InputReader, OutputWriter
from ..diagnostics import TinyRuntimeError

STAGES = (
    ("source", "Source Code"),
    ("lexical", "Lexical Analysis / Tokens"),
    ("syntax", "Syntax Analysis / AST"),
    ("semantic", "Semantic Analysis"),
    ("symbols", "Symbol Table"),
    ("ir", "Intermediate Code"),
    ("code", "Target / VM Code"),
    ("execution", "Execution / Diagnostics"),
)
NAVIGATION = STAGES + (("pipeline", "Compiler Pipeline"), ("cfg", "Control Flow Graph"),
                       ("trace", "Execution Trace"), ("library", "Examples / Program Library"),
                       ("complexity", "Complexity Analysis"))


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class InputRequest:
    execution_id: str
    sequence: int
    name: str


@dataclass
class RunSession:
    source: str
    filename: str = "<untitled>"
    run_id: str = field(default_factory=lambda: uuid4().hex[:8])
    result: Optional[CompilationResult] = None
    statuses: dict = field(default_factory=lambda: {key: "pending" for key, _ in STAGES})
    output: str = ""
    runtime_error: str = ""
    steps: int = 0
    memory: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    cfg: object = None
    trace: list = field(default_factory=list)
    trace_truncated: bool = False
    enrichment_errors: list = field(default_factory=list)
    complexity: object = None
    revision: int = 0
    execution_id: str = ""

    def stale(self, source: str) -> bool:
        return self.source != source


class InteractiveReader(InputReader):
    """Wait only in the worker; UI submission uses a thread-safe queue."""

    def __init__(self, queue: Queue, cancelled: Event, prompt, resumed=None) -> None:
        super().__init__()
        self.queue = queue
        self.cancelled = cancelled
        self.prompt = prompt
        self.resumed = resumed

    def _next_token(self, name):
        while not self._pending:
            self.prompt(name)
            while True:
                if self.cancelled.is_set():
                    raise Cancelled()
                try:
                    text = self.queue.get(timeout=0.05)
                    if text is None:
                        return None
                    if self.resumed:
                        self.resumed(text)
                    break
                except Empty:
                    continue
            self._pending = text.lstrip("\ufeff").split()
        return self._pending.pop(0)


class StreamingWriter(OutputWriter):
    """Retain exact output and stream it to the GUI through a signal."""

    def __init__(self, emit) -> None:
        super().__init__()
        self.emit = emit
        self._buffer = []
        self._size = 0
        self._last_emit = 0.0

    def write(self, text):
        super().write(text)
        self._buffer.append(text)
        self._size += len(text)
        if self._size >= 4096 or monotonic() - self._last_emit >= 0.03:
            self.flush()

    def flush(self):
        if self._buffer:
            self.emit("".join(self._buffer))
            self._buffer.clear()
            self._size = 0
            self._last_emit = monotonic()
