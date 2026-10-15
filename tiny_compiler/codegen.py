"""Target code generation: three-address code -> stack-machine bytecode.

The target is a small stack machine (executed by ``vm.py``; this project does
*not* produce native machine code).  Instruction set:

    PUSH v        push constant (int or bool)
    LOAD x        push the value of variable x
    STORE x       pop into variable x
    ADD SUB MUL DIV MOD            pop b, pop a, push a <op> b
    LT LE GT GE EQ NE              pop b, pop a, push the bool result
    NEG NOT                        unary operators
    JMP n         jump to instruction index n
    JZ n          pop; jump to n if the value is false
    JNZ n         pop; jump to n if the value is true
    READ_INT x / READ_BOOL x       read a value from input into x
    PRINT         pop and print a value
    PRINT_STR s   print a string literal
    PRINT_SPACE   print one space
    PRINT_NL      print a newline
    HALT          stop
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import ir as I

BIN_TO_OP = {
    "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
    "<": "LT", "<=": "LE", ">": "GT", ">=": "GE", "==": "EQ", "!=": "NE",
}
OP_TO_BIN = {v: k for k, v in BIN_TO_OP.items()}


class VMInstr:
    __slots__ = ("op", "arg", "line")

    def __init__(self, op: str, arg=None, line: int = 0) -> None:
        self.op = op
        self.arg = arg
        self.line = line

    def __repr__(self) -> str:
        return "VMInstr(%s)" % format_vm_instr(self)

    def __eq__(self, other) -> bool:
        return isinstance(other, VMInstr) and other.op == self.op \
            and type(other.arg) is type(self.arg) and other.arg == self.arg

    def __hash__(self) -> int:
        return hash((self.op, type(self.arg), self.arg))


def format_vm_instr(ins: VMInstr) -> str:
    if ins.arg is None:
        return ins.op
    if ins.op == "PRINT_STR":
        return "%s %s" % (ins.op, I._quote(ins.arg))
    if ins.op == "PUSH":
        return "%s %s" % (ins.op, "true" if ins.arg is True else
                          "false" if ins.arg is False else ins.arg)
    return "%s %s" % (ins.op, ins.arg)


def format_code(code: List[VMInstr]) -> str:
    return "\n".join("%04d  %s" % (i, format_vm_instr(ins)) for i, ins in enumerate(code))


def _push(operand, line: int) -> VMInstr:
    if isinstance(operand, I.Const):
        return VMInstr("PUSH", operand.value, line)
    return VMInstr("LOAD", operand, line)


def generate_code(tac: List[I.Instr]) -> List[VMInstr]:
    """Two passes: emit with symbolic jump targets, then resolve labels."""
    code: List[VMInstr] = []
    label_addr: Dict[str, int] = {}
    fixups: List[VMInstr] = []

    for ins in tac:
        op, ln = ins.op, ins.line
        if op == I.LABEL:
            label_addr[ins.dst] = len(code)
        elif op == I.COPY:
            code.append(_push(ins.a, ln))
            code.append(VMInstr("STORE", ins.dst, ln))
        elif op == I.BIN:
            code.append(_push(ins.a, ln))
            code.append(_push(ins.b, ln))
            code.append(VMInstr(BIN_TO_OP[ins.bin_op], None, ln))
            code.append(VMInstr("STORE", ins.dst, ln))
        elif op in (I.NEG, I.NOT):
            code.append(_push(ins.a, ln))
            code.append(VMInstr("NEG" if op == I.NEG else "NOT", None, ln))
            code.append(VMInstr("STORE", ins.dst, ln))
        elif op == I.GOTO:
            j = VMInstr("JMP", ins.dst, ln)
            code.append(j)
            fixups.append(j)
        elif op in (I.IFFALSE, I.IFTRUE):
            code.append(_push(ins.a, ln))
            j = VMInstr("JZ" if op == I.IFFALSE else "JNZ", ins.dst, ln)
            code.append(j)
            fixups.append(j)
        elif op == I.READ:
            code.append(VMInstr("READ_INT" if ins.type == "int" else "READ_BOOL", ins.dst, ln))
        elif op == I.WRITE:
            code.append(_push(ins.a, ln))
            code.append(VMInstr("PRINT", None, ln))
        elif op == I.WRITES:
            code.append(VMInstr("PRINT_STR", ins.a, ln))
        elif op == I.SPACE:
            code.append(VMInstr("PRINT_SPACE", None, ln))
        elif op == I.NEWLINE:
            code.append(VMInstr("PRINT_NL", None, ln))
        elif op == I.HALT:
            code.append(VMInstr("HALT", None, ln))
        else:  # pragma: no cover
            raise ValueError("unknown TAC op %r" % op)

    for j in fixups:
        j.arg = label_addr[j.arg]
    return code
