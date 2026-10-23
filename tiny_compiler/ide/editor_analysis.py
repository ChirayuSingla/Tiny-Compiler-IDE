"""Versioned, debounced compilation for editor diagnostics and all stage views."""
from copy import deepcopy
from PySide6.QtCore import QThread, Signal

from ..pipeline import compile_source
from ..semantic import analyze
from ..diagnostics import DiagnosticBag
from ..control_flow import build_cfg
from ..complexity import analyze_complexity
from .session import RunSession


class EditorAnalysis(QThread):
    ready = Signal(str, object)
    snapshot = Signal(object)
    completed = Signal(object)

    def __init__(self, source, parent=None, revision=0, filename="<untitled>"):
        super().__init__(parent)
        self.source = source
        self.session = RunSession(source, filename, revision=revision)

    def run(self):
        session = self.session
        def progress(key, status, result):
            if self.isInterruptionRequested():
                raise InterruptedError()
            session.result = result
            session.statuses[key] = status
            self.snapshot.emit(deepcopy(session))
        try:
            result = compile_source(self.source, progress)
            session.result = result
            for key, status in session.statuses.items():
                if status == "pending":
                    session.statuses[key] = "not run" if key == "execution" and result.ok else "blocked"
            if self.isInterruptionRequested():
                return
            if result.ir is not None:
                try:
                    session.cfg = build_cfg(result.ir)
                except Exception as exc:
                    session.enrichment_errors.append("CFG unavailable: %s" % exc)
            try:
                session.complexity = analyze_complexity(result)
            except Exception as exc:
                session.enrichment_errors.append("Complexity unavailable: %s" % exc)
            if self.isInterruptionRequested():
                return
            self.completed.emit(deepcopy(session))
            # The parser can recover declarations from partial statements.
            # Analyze that recovered AST for completion only; retain original
            # compiler diagnostics and never alter an IDE run snapshot.
            completion_result = deepcopy(result)
            if completion_result.ast is not None and completion_result.symbols is None and not self.isInterruptionRequested():
                try:
                    completion_result.symbols = analyze(completion_result.ast, DiagnosticBag())
                except Exception:
                    # Partial-source completion is optional; its failure cannot
                    # invalidate the actual compilation already published.
                    completion_result = result
            if not self.isInterruptionRequested():
                self.ready.emit(self.source, completion_result)
        except InterruptedError:
            pass
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            from ..pipeline import CompilationResult
            if session.result is None:
                session.result = CompilationResult(self.source)
            session.result.diagnostics.error("internal", "Compiler error: %s" % exc, 1, 1)
            for key, status in session.statuses.items():
                if status == "active":
                    session.statuses[key] = "error"
                elif status == "pending":
                    session.statuses[key] = "blocked"
            self.completed.emit(deepcopy(session))
            self.ready.emit(self.source, None)
