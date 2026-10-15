"""Three-address code (TAC): generation, pretty printing and a reference interpreter.

Instruction forms (``dst``/``a``/``b`` are variable names, temporaries such
as ``$t3``, or ``Const`` values):

    COPY   dst = a
    BIN    dst = a <op> b          op in + - * / % < <= > >= == !=
    NEG    dst = - a
    NOT    dst = not a
    LABEL  L3:
    GOTO   goto L3
    IFFALSE ifFalse a goto L3
    IFTRUE  ifTrue  a goto L3
    READ   read dst                (typed: int or bool)
    WRITE  write a                 (prints a value, no newline)
    WRITES write "text"            (prints a string literal)
    SPACE  write ' '               (separator between items of one 'write')
    NEWLINE newline
    HALT   halt
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from . import ast_nodes as A
from .diagnostics import TinyRuntimeError
from .runtime import (DEFAULT_MAX_STEPS, InputReader, OutputWriter, apply_binary,
                      apply_unary, format_value, too_many_steps)

BIN_OPS = ("+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=")

COPY = "COPY"
BIN = "BIN"
NEG = "NEG"
NOT = "NOT"
LABEL = "LABEL"
GOTO = "GOTO"
IFFALSE = "IFFALSE"
IFTRUE = "IFTRUE"
READ = "READ"
WRITE = "WRITE"
WRITES = "WRITES"
SPACE = "SPACE"
NEWLINE = "NEWLINE"
HALT = "HALT"


class Const:
    """A literal operand (int or bool)."""

    __slots__ = ("value",)

    def __init__(self, value) -> None:
        self.value = value

    def __repr__(self) -> str:
        return "Const(%r)" % (self.value,)

    def __eq__(self, other) -> bool:
        return isinstance(other, Const) and type(other.value) is type(self.value) \
            and other.value == self.value

    def __hash__(self) -> int:
        return hash((type(self.value), self.value))

    def __str__(self) -> str:
        return format_value(self.value)


def operand_str(x) -> str:
    return str(x)


class Instr:
    __slots__ = ("op", "dst", "a", "b", "bin_op", "type", "line")

    def __init__(self, op: str, dst=None, a=None, b=None, bin_op: Optional[str] = None,
                 type_: Optional[str] = None, line: int = 0) -> None:
        self.op = op
        self.dst = dst
        self.a = a
        self.b = b
        self.bin_op = bin_op
        self.type = type_  # value type for READ
        self.line = line

    def __repr__(self) -> str:
        return "Instr(%s)" % format_instr(self)

    def __eq__(self, other) -> bool:
        return isinstance(other, Instr) and format_instr(self) == format_instr(other)

    def __hash__(self) -> int:
        return hash(format_instr(self))


def _quote(s: str) -> str:
    return '"%s"' % s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t") \
        .replace('"', '\\"')


def format_instr(i: Instr) -> str:
    if i.op == COPY:
        return "%s = %s" % (i.dst, i.a)
    if i.op == BIN:
        return "%s = %s %s %s" % (i.dst, i.a, i.bin_op, i.b)
    if i.op == NEG:
        return "%s = - %s" % (i.dst, i.a)
    if i.op == NOT:
        return "%s = not %s" % (i.dst, i.a)
    if i.op == LABEL:
        return "%s:" % i.dst
    if i.op == GOTO:
        return "goto %s" % i.dst
    if i.op == IFFALSE:
        return "ifFalse %s goto %s" % (i.a, i.dst)
    if i.op == IFTRUE:
        return "ifTrue %s goto %s" % (i.a, i.dst)
    if i.op == READ:
        return "read %s" % i.dst
    if i.op == WRITE:
        return "write %s" % i.a
    if i.op == WRITES:
        return "write %s" % _quote(i.a)
    if i.op == SPACE:
        return "write ' '"
    if i.op == NEWLINE:
        return "newline"
    if i.op == HALT:
        return "halt"
    raise ValueError("unknown TAC op %r" % i.op)


def format_ir(instrs: List[Instr]) -> str:
    rows = []
    for ins in instrs:
        text = format_instr(ins)
        rows.append(text if ins.op == LABEL else "    " + text)
    return "\n".join(rows)


# ---------------------------------------------------------------------------
class IRGenerator:
    """Translate an analysed AST into a flat list of TAC instructions."""

    def __init__(self) -> None:
        self.code: List[Instr] = []
        self._temps = 0
        self._labels = 0

    def new_temp(self) -> str:
        self._temps += 1
        return "$t%d" % self._temps

    def new_label(self) -> str:
        self._labels += 1
        return "L%d" % self._labels

    def emit(self, *args, **kwargs) -> Instr:
        ins = Instr(*args, **kwargs)
        self.code.append(ins)
        return ins

    def generate(self, program: A.Program) -> List[Instr]:
        for st in program.statements:
            self._stmt(st)
        self.emit(HALT)
        return self.code

    # -- statements ----------------------------------------------------------
    def _stmt(self, st) -> None:
        if isinstance(st, A.VarDecl):
            sym = st.symbol
            if st.init is not None:
                val = self._expr(st.init)
            else:
                val = Const(0 if st.type_name == "int" else False)
            self.emit(COPY, dst=sym.unique, a=val, line=st.line)
        elif isinstance(st, A.Assign):
            val = self._expr(st.value)
            self.emit(COPY, dst=st.symbol.unique, a=val, line=st.line)
        elif isinstance(st, A.Block):
            for s in st.statements:
                self._stmt(s)
        elif isinstance(st, A.If):
            self._if(st)
        elif isinstance(st, A.While):
            start, end = self.new_label(), self.new_label()
            self.emit(LABEL, dst=start, line=st.line)
            cond = self._expr(st.cond)
            self.emit(IFFALSE, dst=end, a=cond, line=st.line)
            self._stmt(st.body)
            self.emit(GOTO, dst=start, line=st.line)
            self.emit(LABEL, dst=end, line=st.line)
        elif isinstance(st, A.Read):
            self.emit(READ, dst=st.symbol.unique, type_=st.symbol.type, line=st.line)
        elif isinstance(st, A.Write):
            for n, item in enumerate(st.items):
                if n > 0:
                    self.emit(SPACE, line=st.line)
                if isinstance(item, A.StringLit):
                    self.emit(WRITES, a=item.value, line=st.line)
                else:
                    self.emit(WRITE, a=self._expr(item), line=st.line)
            self.emit(NEWLINE, line=st.line)
        else:  # pragma: no cover
            raise AssertionError("unknown statement %r" % (st,))

    def _if(self, st: A.If) -> None:
        cond = self._expr(st.cond)
        if st.else_branch is None:
            end = self.new_label()
            self.emit(IFFALSE, dst=end, a=cond, line=st.line)
            self._stmt(st.then_block)
            self.emit(LABEL, dst=end, line=st.line)
        else:
            else_l, end = self.new_label(), self.new_label()
            self.emit(IFFALSE, dst=else_l, a=cond, line=st.line)
            self._stmt(st.then_block)
            self.emit(GOTO, dst=end, line=st.line)
            self.emit(LABEL, dst=else_l, line=st.line)
            self._stmt(st.else_branch)
            self.emit(LABEL, dst=end, line=st.line)

    # -- expressions: return the operand holding the value ---------------------
    def _expr(self, e):
        if isinstance(e, A.IntLit):
            return Const(e.value)
        if isinstance(e, A.BoolLit):
            return Const(e.value)
        if isinstance(e, A.VarRef):
            return e.symbol.unique
        if isinstance(e, A.Unary):
            v = self._expr(e.operand)
            t = self.new_temp()
            self.emit(NEG if e.op == "-" else NOT, dst=t, a=v, line=e.line)
            return t
        if isinstance(e, A.Binary):
            if e.op in ("and", "or"):
                return self._short_circuit(e)
            left = self._expr(e.left)
            right = self._expr(e.right)
            t = self.new_temp()
            self.emit(BIN, dst=t, a=left, b=right, bin_op=e.op, line=e.line)
            return t
        raise AssertionError("unknown expression %r" % (e,))  # pragma: no cover

    def _short_circuit(self, e: A.Binary):
        """`a and b` / `a or b`: the right operand is evaluated only if needed."""
        result = self.new_temp()
        end = self.new_label()
        left = self._expr(e.left)
        self.emit(COPY, dst=result, a=left, line=e.line)
        self.emit(IFFALSE if e.op == "and" else IFTRUE, dst=end, a=result, line=e.line)
        right = self._expr(e.right)
        self.emit(COPY, dst=result, a=right, line=e.line)
        self.emit(LABEL, dst=end, line=e.line)
        return result


def generate_ir(program: A.Program) -> List[Instr]:
    return IRGenerator().generate(program)


# ---------------------------------------------------------------------------
def interpret_tac(instrs: List[Instr], reader: Optional[InputReader] = None,
                  out: Optional[OutputWriter] = None,
                  max_steps: int = DEFAULT_MAX_STEPS) -> OutputWriter:
    """Reference interpreter for TAC.

    It is independent of the stack-VM back-end; the test-suite runs programs
    through both and checks that their behaviour is identical.
    """
    reader = reader if reader is not None else InputReader()
    out = out if out is not None else OutputWriter()
    labels: Dict[str, int] = {}
    for idx, ins in enumerate(instrs):
        if ins.op == LABEL:
            labels[ins.dst] = idx
    mem: Dict[str, object] = {}

    def val(x):
        return x.value if isinstance(x, Const) else mem[x]

    pc = 0
    steps = 0
    while pc < len(instrs):
        ins = instrs[pc]
        steps += 1
        if steps > max_steps:
            raise too_many_steps(max_steps, ins.line)
        op = ins.op
        pc += 1
        if op == COPY:
            mem[ins.dst] = val(ins.a)
        elif op == BIN:
            mem[ins.dst] = apply_binary(ins.bin_op, val(ins.a), val(ins.b), ins.line)
        elif op == NEG:
            mem[ins.dst] = apply_unary("neg", val(ins.a))
        elif op == NOT:
            mem[ins.dst] = apply_unary("not", val(ins.a))
        elif op == LABEL:
            pass
        elif op == GOTO:
            pc = labels[ins.dst]
        elif op == IFFALSE:
            if not val(ins.a):
                pc = labels[ins.dst]
        elif op == IFTRUE:
            if val(ins.a):
                pc = labels[ins.dst]
        elif op == READ:
            mem[ins.dst] = reader.read_value(ins.type, ins.dst.split("#")[0], ins.line)
        elif op == WRITE:
            out.write(format_value(val(ins.a)))
        elif op == WRITES:
            out.write(ins.a)
        elif op == SPACE:
            out.write(" ")
        elif op == NEWLINE:
            out.write("\n")
        elif op == HALT:
            break
        else:  # pragma: no cover
            raise ValueError("unknown TAC op %r" % op)
    return out
