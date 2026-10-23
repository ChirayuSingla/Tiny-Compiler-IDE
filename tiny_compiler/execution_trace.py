"""Structured, bounded snapshots of the real VM, separate from CLI text tracing."""
from dataclasses import dataclass

TRACE_LIMIT = 2000
STATE_LIMIT = 256


@dataclass(frozen=True)
class TraceStep:
    step: int
    pc: int
    next_pc: int
    instruction: str
    line: int
    memory: dict
    stack: tuple
    output: str
    error: str = ""
    state_truncated: bool = False


def snapshot(machine, pc, next_pc, instruction, output="", error=""):
    """Capture post-instruction state, or state at a failed instruction."""
    return TraceStep(machine.steps, pc, next_pc, str(instruction), machine.code[pc].line,
                     dict(list(machine.memory.items())[:STATE_LIMIT]),
                     tuple(machine.stack[-STATE_LIMIT:]), output[:4096], error,
                     len(machine.memory) > STATE_LIMIT or len(machine.stack) > STATE_LIMIT
                     or len(output) > 4096)
