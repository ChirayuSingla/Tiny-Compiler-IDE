"""Basic blocks and control-flow edges derived from real three-address code."""
from dataclasses import dataclass, field
from typing import List

from .ir import LABEL, GOTO, IFFALSE, IFTRUE, HALT, format_instr


@dataclass
class BasicBlock:
    id: int
    start: int
    end: int
    instructions: List[str]
    source_lines: List[int]
    reachable: bool = False

    @property
    def text(self):
        return "\n".join("%04d  %s" % (self.start + i, text)
                         for i, text in enumerate(self.instructions))


@dataclass(frozen=True)
class FlowEdge:
    source: int
    target: int
    label: str


@dataclass
class ControlFlowGraph:
    blocks: List[BasicBlock] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)


def build_cfg(instructions):
    """Use leader partitioning; include short-circuit branches and unreachable code."""
    graph = ControlFlowGraph()
    if not instructions:
        return graph
    labels = {ins.dst: index for index, ins in enumerate(instructions) if ins.op == LABEL}
    leaders = {0}
    for index, ins in enumerate(instructions):
        if ins.op in (GOTO, IFFALSE, IFTRUE):
            if ins.dst not in labels:
                raise ValueError("Unknown IR jump label %r" % ins.dst)
            leaders.add(labels[ins.dst])
        if ins.op in (GOTO, IFFALSE, IFTRUE, HALT) and index + 1 < len(instructions):
            leaders.add(index + 1)
    starts = sorted(leaders)
    owner = {}
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(instructions)
        block = BasicBlock(number, start, end,
                           [format_instr(i) for i in instructions[start:end]],
                           sorted({i.line for i in instructions[start:end] if i.line}))
        graph.blocks.append(block)
        for index in range(start, end):
            owner[index] = number
    for block in graph.blocks:
        last = instructions[block.end - 1]
        following = block.id + 1
        if last.op in (GOTO, IFFALSE, IFTRUE):
            label = {GOTO: "jump", IFFALSE: "false", IFTRUE: "true"}[last.op]
            graph.edges.append(FlowEdge(block.id, owner[labels[last.dst]], label))
        if last.op not in (GOTO, HALT) and following < len(graph.blocks):
            label = {IFFALSE: "true", IFTRUE: "false"}.get(last.op, "next")
            graph.edges.append(FlowEdge(block.id, following, label))
    pending = [0]
    while pending:
        current = pending.pop()
        if graph.blocks[current].reachable:
            continue
        graph.blocks[current].reachable = True
        pending.extend(e.target for e in graph.edges if e.source == current)
    return graph
