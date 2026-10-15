"""A small stack-based virtual machine that executes ``codegen`` bytecode."""
from __future__ import annotations

from typing import Dict, List, Optional, TextIO

from .codegen import OP_TO_BIN, VMInstr, format_vm_instr
from .diagnostics import TinyRuntimeError
from .runtime import (DEFAULT_MAX_STEPS, InputReader, OutputWriter, apply_binary,
                      apply_unary, format_value, too_many_steps)


class VM:
    def __init__(self, code: List[VMInstr], reader: Optional[InputReader] = None,
                 out: Optional[OutputWriter] = None, max_steps: int = DEFAULT_MAX_STEPS,
                 trace: Optional[TextIO] = None) -> None:
        self.code = code
        self.reader = reader if reader is not None else InputReader()
        self.out = out if out is not None else OutputWriter()
        self.max_steps = max_steps
        self.trace = trace
        self.stack: List[object] = []
        self.memory: Dict[str, object] = {}
        self.steps = 0

    def _pop(self, ins: VMInstr):
        if not self.stack:  # indicates a compiler bug, not a user error
            raise TinyRuntimeError("internal error: stack underflow at '%s'"
                                   % format_vm_instr(ins), ins.line)
        return self.stack.pop()

    def run(self) -> OutputWriter:
        code = self.code
        pc = 0
        while pc < len(code):
            ins = code[pc]
            self.steps += 1
            if self.steps > self.max_steps:
                raise too_many_steps(self.max_steps, ins.line)
            if self.trace is not None:
                self.trace.write("%04d  %-22s stack=%s\n"
                                 % (pc, format_vm_instr(ins),
                                    [format_value(v) for v in self.stack]))
            op = ins.op
            pc += 1
            if op == "PUSH":
                self.stack.append(ins.arg)
            elif op == "LOAD":
                self.stack.append(self.memory[ins.arg])
            elif op == "STORE":
                self.memory[ins.arg] = self._pop(ins)
            elif op in OP_TO_BIN:
                b = self._pop(ins)
                a = self._pop(ins)
                self.stack.append(apply_binary(OP_TO_BIN[op], a, b, ins.line))
            elif op == "NEG":
                self.stack.append(apply_unary("neg", self._pop(ins)))
            elif op == "NOT":
                self.stack.append(apply_unary("not", self._pop(ins)))
            elif op == "JMP":
                pc = ins.arg
            elif op == "JZ":
                if not self._pop(ins):
                    pc = ins.arg
            elif op == "JNZ":
                if self._pop(ins):
                    pc = ins.arg
            elif op == "READ_INT":
                self.memory[ins.arg] = self.reader.read_value("int", ins.arg.split("#")[0],
                                                              ins.line)
            elif op == "READ_BOOL":
                self.memory[ins.arg] = self.reader.read_value("bool", ins.arg.split("#")[0],
                                                              ins.line)
            elif op == "PRINT":
                self.out.write(format_value(self._pop(ins)))
            elif op == "PRINT_STR":
                self.out.write(ins.arg)
            elif op == "PRINT_SPACE":
                self.out.write(" ")
            elif op == "PRINT_NL":
                self.out.write("\n")
            elif op == "HALT":
                break
            else:  # pragma: no cover
                raise TinyRuntimeError("internal error: unknown instruction %r" % op, ins.line)
        return self.out
