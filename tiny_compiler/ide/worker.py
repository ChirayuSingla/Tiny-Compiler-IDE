"""One worker owns one compilation and executes that exact generated code."""
from copy import deepcopy
from queue import Queue
from threading import Event, Lock
from time import monotonic
from uuid import uuid4

from PySide6.QtCore import QThread, Signal

from ..diagnostics import TinyRuntimeError
from ..pipeline import compile_source
from ..vm import VM
from ..control_flow import build_cfg
from ..execution_trace import TRACE_LIMIT
from ..complexity import analyze_complexity
from .session import Cancelled, InputRequest, InteractiveReader, RunSession, StreamingWriter


class CompilerWorker(QThread):
    snapshot = Signal(object)
    output = Signal(str)
    input_requested = Signal(object)
    diagnostic = Signal(str)
    completed = Signal(object)
    trace_ready = Signal(object)

    def __init__(self, source, filename="<untitled>", execute=False, max_steps=5_000_000,
                 parent=None, compiled=None, revision=0):
        super().__init__(parent)
        self.reused_compilation = bool(compiled and compiled.source == source and
                                       compiled.revision == revision and compiled.result and compiled.result.ok)
        self.session = deepcopy(compiled) if self.reused_compilation else RunSession(source, filename, revision=revision)
        self.session.output = ""
        self.session.runtime_error = ""
        self.session.steps = 0
        self.session.memory = {}
        self.session.inputs = []
        self.session.trace = []
        self.session.trace_truncated = False
        self.session.statuses["execution"] = "pending"
        self.session.execution_id = uuid4().hex[:8] if execute else ""
        self.execute = execute
        self.max_steps = max_steps
        self.cancelled = Event()
        self.input_queue = Queue()
        self._trace_batch = []
        self._trace_time = monotonic()
        self._input_lock = Lock()
        self._pending_request = None
        self._request_sequence = 0

    def cancel(self):
        self.cancelled.set()

    def submit(self, text, request=None):
        with self._input_lock:
            pending = self._pending_request
            if self.cancelled.is_set() or pending is None or (request is not None and request != pending):
                return False
            self._pending_request = None
            self.input_queue.put(text)
            return True

    def publish(self):
        # The receiver never shares mutable ASTs/symbols with the worker.
        if hasattr(self, "writer"):
            self.session.output = self.writer.getvalue()
        self.snapshot.emit(deepcopy(self.session))

    def stage(self, key, status, result):
        if self.cancelled.is_set():
            raise Cancelled()
        self.session.result = result
        self.session.statuses[key] = status
        self.publish()

    def prompt(self, name):
        self.writer.flush()
        self.flush_trace()
        self.session.statuses["execution"] = "waiting"
        self.publish()
        with self._input_lock:
            self._request_sequence += 1
            request = InputRequest(self.session.execution_id, self._request_sequence, name)
            self._pending_request = request
        self.input_requested.emit(request)

    def resumed(self, text):
        self.session.inputs.append(text)
        self.session.statuses["execution"] = "active"
        self.publish()

    def record_step(self, entry):
        self.session.trace.append(entry)
        self._trace_batch.append(entry)
        if len(self._trace_batch) >= 64 or monotonic() - self._trace_time > 0.06:
            self.flush_trace()
        return len(self.session.trace) < TRACE_LIMIT

    def flush_trace(self):
        if self._trace_batch:
            self.trace_ready.emit((self.session.execution_id or self.session.run_id, deepcopy(self._trace_batch)))
            self._trace_batch.clear()
            self._trace_time = monotonic()

    def run(self):
        session = self.session
        writer = StreamingWriter(self.output.emit)
        self.writer = writer
        machine = None
        try:
            if not self.reused_compilation:
                session.result = compile_source(session.source, self.stage)
            if session.result.ir is not None:
                try:
                    session.cfg = build_cfg(session.result.ir)
                except Exception as exc:
                    session.enrichment_errors.append("CFG unavailable: %s" % exc)
            if self.cancelled.is_set():
                raise Cancelled()
            try:
                session.complexity = analyze_complexity(session.result)
            except Exception as exc:
                session.enrichment_errors.append("Complexity analysis unavailable: %s" % exc)
            if not session.result.ok:
                for key, status in session.statuses.items():
                    if status == "pending":
                        session.statuses[key] = "blocked"
                for diag in session.result.diagnostics.sorted():
                    self.diagnostic.emit(diag.format(session.source, session.filename))
            elif self.execute:
                if self.cancelled.is_set():
                    raise Cancelled()
                session.statuses["execution"] = "active"
                self.publish()
                reader = InteractiveReader(self.input_queue, self.cancelled, self.prompt, self.resumed)
                machine = VM(session.result.code, reader, writer,
                             max_steps=self.max_steps, should_stop=self.cancelled.is_set,
                             on_step=self.record_step)
                machine.run()
                session.statuses["execution"] = "completed"
            else:
                session.statuses["execution"] = "not run"
            if session.result.ok:
                for diag in session.result.diagnostics.warnings:
                    self.diagnostic.emit(diag.format(session.source, session.filename))
        except Cancelled:
            writer.flush()
            session.runtime_error = "Operation cancelled."
            self.diagnostic.emit(session.runtime_error)
            for key, status in session.statuses.items():
                if status in ("active", "waiting", "pending"):
                    session.statuses[key] = "cancelled"
        except TinyRuntimeError as exc:
            writer.flush()
            session.runtime_error = exc.format(session.filename)
            session.statuses["execution"] = "cancelled" if self.cancelled.is_set() else "error"
            self.diagnostic.emit(session.runtime_error)
        except Exception as exc:
            writer.flush()
            # Qt must never terminate the process on a Python worker exception.
            session.runtime_error = "Internal compiler error: %s: %s" % (type(exc).__name__, exc)
            for key, status in session.statuses.items():
                if status in ("active", "waiting"):
                    session.statuses[key] = "error"
                elif status == "pending":
                    session.statuses[key] = "blocked"
            self.diagnostic.emit(session.runtime_error)
        finally:
            with self._input_lock:
                self._pending_request = None
            writer.flush()
            self.flush_trace()
            session.output = writer.getvalue()
            if machine is not None:
                session.steps = machine.steps
                session.memory = dict(machine.memory)
                session.trace_truncated = machine.steps > len(session.trace)
            self.completed.emit(deepcopy(session))
