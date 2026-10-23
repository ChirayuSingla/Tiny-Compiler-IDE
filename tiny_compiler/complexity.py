"""Conservative asymptotic upper bounds over analyzed Tiny ASTs.

This is a scalar-operation model, not measured runtime or a bit-complexity model.
Only proven monotone counter loops with invariant bounds are accepted.
"""
from dataclasses import dataclass, field
from typing import Optional

from . import ast_nodes as A
from .runtime import apply_binary, apply_unary
from .semantic import eval_const
from .diagnostics import TinyRuntimeError


@dataclass(frozen=True)
class Value:
    constant: object = None
    parameter: Optional[str] = None


UNKNOWN = Value()


def key(node):
    symbol = getattr(node, "symbol", None)
    return symbol.unique if symbol else getattr(node, "name", "?")


def value_of(node, env):
    if isinstance(node, (A.IntLit, A.BoolLit)):
        return Value(node.value)
    if isinstance(node, A.VarRef):
        return env.get(key(node), UNKNOWN)
    if isinstance(node, A.Unary):
        value = value_of(node.operand, env)
        if value.constant is not None:
            return Value(apply_unary("neg" if node.op == "-" else node.op, value.constant))
    if isinstance(node, A.Binary):
        left, right = value_of(node.left, env), value_of(node.right, env)
        if left.constant is not None and right.constant is not None:
            try:
                if node.op == "and":
                    return Value(left.constant and right.constant)
                if node.op == "or":
                    return Value(left.constant or right.constant)
                return Value(apply_binary(node.op, left.constant, right.constant))
            except (ArithmeticError, ValueError, TinyRuntimeError):
                # Runtime failures are not constant values.
                return UNKNOWN
    return UNKNOWN


@dataclass(frozen=True)
class Cost:
    # A sum of products: term entries are (parameter, polynomial power, log power).
    terms: tuple = ((),)
    unknown: bool = False

    @staticmethod
    def parameter(name, logarithmic=False):
        return Cost((((name, 0 if logarithmic else 1, 1 if logarithmic else 0),),))

    def plus(self, other):
        if self.unknown or other.unknown:
            return Cost(unknown=True)
        terms = set(self.terms + other.terms)
        def dominates(a, b):
            da = {name: (p, log) for name, p, log in a}
            db = {name: (p, log) for name, p, log in b}
            return all(da.get(name, (0, 0)) >= power for name, power in db.items())
        return Cost(tuple(sorted(t for t in terms if not any(s != t and dominates(s, t) for s in terms))))

    def times(self, other):
        if self.unknown or other.unknown:
            return Cost(unknown=True)
        result = None
        for a in self.terms:
            for b in other.terms:
                powers = {}
                for name, p, log in a + b:
                    x, y = powers.get(name, (0, 0))
                    powers[name] = (x + p, y + log)
                term = Cost((tuple((name, p, log) for name, (p, log) in sorted(powers.items())),))
                result = term if result is None else result.plus(term)
        return result or Cost()

    def notation(self):
        if self.unknown:
            return "Unable to determine"
        terms = []
        for term in self.terms:
            factors = []
            for name, power, logs in term:
                if power:
                    factors.append(name if power == 1 else name + "^" + str(power))
                if logs:
                    factors.append("log " + name if logs == 1 else "(log " + name + ")^" + str(logs))
            terms.append(" * ".join(factors) or "1")
        return "O(" + " + ".join(terms) + ")"


@dataclass
class LoopFinding:
    line: int
    depth: int
    counter: str
    pattern: str
    iterations: str
    time: str
    reason: str


@dataclass
class ComplexityReport:
    time: str = "Unable to determine"
    auxiliary_space: str = "Unable to determine"
    confidence: str = "Unavailable"
    loops: list = field(default_factory=list)
    parameters: list = field(default_factory=list)
    declared_slots: int = 0
    temporary_slots: int = 0
    reasons: list = field(default_factory=list)
    assumptions: list = field(default_factory=lambda: [
        "Asymptotic upper bound in a unit-cost scalar-operation model; each AST operation costs O(1).",
        "Input symbols denote magnitudes of runtime integer values, at least 1; log terms use log(max(2, magnitude)).",
        "Source size is fixed. Estimates describe successful executions under the recognized loop recurrences.",
        "Auxiliary space counts scalar storage slots and bounded expression stack, excluding input/output buffers, IDE trace, and compiler artifacts.",
    ])
    limitations: list = field(default_factory=lambda: [
        "These are estimates, not exact execution time or exact memory consumption.",
        "Python integers have arbitrary precision: O(1) scalar slots does not imply O(1) bits or bytes.",
        "Bit costs of arithmetic, integer input/output and printed-value size are not analyzed.",
        "Only invariant simple bounds and one unconditional counter update are supported. Ambiguous termination, compound conditions, dependent nested bounds and multiple counter updates are rejected.",
    ])

    def text(self):
        lines = ["Estimated asymptotic time: " + self.time,
                 "Estimated auxiliary space: " + self.auxiliary_space,
                 "Confidence: " + self.confidence, "",
                 "Static scalar storage: %d declared identities + %d IR temporaries." % (
                     self.declared_slots, self.temporary_slots),
                 "Bit-level auxiliary space: Unable to determine", "",
                 "Input parameters: " + (", ".join(self.parameters) or "none"), "", "Reasoning"]
        lines += self.reasons or ["No supported analysis available."]
        for loop in self.loops:
            lines += ["", "Line %d | nesting depth %d | counter %s" % (loop.line, loop.depth, loop.counter),
                      "%s: %s iterations; loop time %s" % (loop.pattern, loop.iterations, loop.time), loop.reason]
        lines += ["", "Assumptions"] + ["• " + s for s in self.assumptions]
        lines += ["", "Confidence and limitations"] + ["• " + s for s in self.limitations]
        lines += ["", "Measured runtime is separate: see Execution Results for actual instruction counts."]
        return "\n".join(lines)


def written(nodes):
    """All storage identities assigned anywhere, including conditionals and loops."""
    result = []
    for node in nodes:
        if isinstance(node, (A.Assign, A.Read, A.VarDecl)):
            result.append((key(node), node))
        elif isinstance(node, A.Block):
            result.extend(written(node.statements))
        elif isinstance(node, A.While):
            result.extend(written(node.body.statements))
        elif isinstance(node, A.If):
            result.extend(written(node.then_block.statements))
            if node.else_branch:
                result.extend(written([node.else_branch]))
    return result


def unconditional_assignments(nodes):
    result = []
    for node in nodes:
        if isinstance(node, A.Assign):
            result.append(node)
        elif isinstance(node, A.Block):
            result.extend(unconditional_assignments(node.statements))
    return result


class Analyzer:
    def __init__(self, result):
        self.result = result
        self.report = ComplexityReport()
        self.params = set()

    def analyze(self):
        if not self.result.ok:
            self.report.reasons.append("Compile a semantically valid program before complexity analysis.")
            return self.report
        cost, _ = self.statements(self.result.ast.statements, {}, 0)
        self.report.time = cost.notation()
        self.report.auxiliary_space = "O(1) scalar slots"
        self.report.declared_slots = len(self.result.symbols.all_symbols)
        self.report.temporary_slots = len({i.dst for i in self.result.ir if isinstance(i.dst, str) and i.dst.startswith("$t")})
        self.report.parameters = sorted(self.params)
        self.report.confidence = "Supported upper bound under stated model" if not cost.unknown else "Time unresolved; scalar-space model supported"
        self.report.reasons.append("Sequential costs are added; alternative branches take an upper bound; supported nested loop factors multiply.")
        if not self.report.loops:
            self.report.reasons.append("No reachable loops were found; the fixed straight-line/conditional program performs O(1) scalar operations.")
        if all(loop.pattern == "fixed bound" for loop in self.report.loops) and self.report.loops:
            self.report.reasons.append("All recognized iteration bounds are literal constants, so their cost is O(1) with respect to runtime inputs.")
        return self.report

    def statements(self, nodes, env, depth):
        total = Cost()
        for node in nodes:
            if isinstance(node, A.VarDecl):
                env[key(node)] = value_of(node.init, env) if node.init is not None else Value(0 if node.type_name == "int" else False)
            elif isinstance(node, A.Assign):
                env[key(node)] = value_of(node.value, env)
            elif isinstance(node, A.Read):
                if node.symbol.type == "int":
                    env[key(node)] = Value(parameter=key(node))
                    self.params.add(key(node))
                else:
                    env[key(node)] = UNKNOWN
            elif isinstance(node, A.Block):
                cost, env = self.statements(node.statements, env, depth)
                total = total.plus(cost)
            elif isinstance(node, A.If):
                test = value_of(node.cond, env)
                alternatives = [node.then_block.statements,
                                [node.else_branch] if node.else_branch else []]
                if isinstance(test.constant, bool):
                    cost, env = self.statements(alternatives[0 if test.constant else 1], env, depth)
                else:
                    left, le = self.statements(alternatives[0], dict(env), depth)
                    right, re = self.statements(alternatives[1], dict(env), depth)
                    cost = left.plus(right)
                    env = {k: le.get(k, UNKNOWN) if le.get(k, UNKNOWN) == re.get(k, UNKNOWN) else UNKNOWN
                           for k in set(le) | set(re)}
                total = total.plus(cost)
            elif isinstance(node, A.While):
                cost = self.loop(node, env, depth + 1)
                total = total.plus(cost)
                for name, _ in written(node.body.statements):
                    env[name] = UNKNOWN
        return total, env

    def loop(self, node, env, depth):
        finding = LoopFinding(node.line, depth, "?", "unsupported", "Unable to determine", "Unable to determine", "")
        self.report.loops.append(finding)
        test = value_of(node.cond, env)
        if test.constant is False:
            finding.pattern, finding.iterations, finding.time = "fixed bound", "0", "O(1)"
            finding.reason = "The entry condition is statically false; the body is unreachable."
            return Cost()

        def reject(reason):
            finding.reason = reason
            return Cost(unknown=True)

        cond = node.cond
        if not isinstance(cond, A.Binary) or cond.op not in ("<", "<=", ">", ">="):
            return reject("Unable to determine: require a single ordered comparison; termination is not established for this condition.")
        op, counter, bound_node = cond.op, cond.left, cond.right
        writes = written(node.body.statements)
        reverse = (isinstance(bound_node, A.VarRef) and
                   (not isinstance(counter, A.VarRef) or
                    (not any(k == key(counter) for k, _ in writes) and
                     any(k == key(bound_node) for k, _ in writes))))
        if reverse:
            counter, bound_node = bound_node, counter
            op = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}[op]
        if not isinstance(counter, A.VarRef):
            return reject("Unable to determine: condition is not a simple counter comparison.")
        name = key(counter)
        finding.counter = name
        updates = [n for k, n in writes if k == name]
        direct = [n for n in unconditional_assignments(node.body.statements) if key(n) == name]
        if len(updates) != 1 or len(direct) != 1 or updates[0] is not direct[0]:
            return reject("Unable to determine: require exactly one unconditional assignment to the counter per iteration.")
        update = direct[0].value
        if not isinstance(update, A.Binary) or not isinstance(update.left, A.VarRef) or key(update.left) != name:
            return reject("Unable to determine: counter update is not counter plus/minus/times/divided by a constant.")
        amount = eval_const(update.right)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            return reject("Unable to determine: require a strictly positive literal-expression update amount.")
        if isinstance(bound_node, A.VarRef) and any(k == key(bound_node) for k, _ in writes):
            return reject("Unable to determine: the loop bound is modified inside the body.")
        initial, bound = env.get(name, UNKNOWN), value_of(bound_node, env)
        if initial == UNKNOWN or bound == UNKNOWN:
            return reject("Unable to determine: initial value or bound is unknown, possibly dependent on an outer counter.")
        if initial.parameter and bound.parameter:
            return reject("Unable to determine: both the initial counter and bound depend on input.")
        factor = None
        if update.op == "+" and op in ("<", "<=") and type(initial.constant) is int:
            factor = Cost.parameter(bound.parameter) if bound.parameter else Cost()
            end = bound.parameter or str(bound.constant)
            finding.iterations = "max(0, ceil((%s - %s%s) / %d))" % (end, initial.constant, " + 1" if op == "<=" else "", amount)
            finding.pattern = "linear increasing"
        elif update.op == "-" and op in (">", ">=") and type(bound.constant) is int:
            factor = Cost.parameter(initial.parameter) if initial.parameter else Cost()
            start = initial.parameter or str(initial.constant)
            finding.iterations = "max(0, ceil((%s - %s%s) / %d))" % (start, bound.constant, " + 1" if op == ">=" else "", amount)
            finding.pattern = "linear decreasing"
        elif update.op == "*" and amount >= 2 and op in ("<", "<=") and type(initial.constant) is int and initial.constant > 0:
            factor = Cost.parameter(bound.parameter, True) if bound.parameter else Cost()
            finding.iterations = "logarithmic in %s (growth factor %d, start %s)" % (bound.parameter or bound.constant, amount, initial.constant)
            finding.pattern = "logarithmic growth"
        elif update.op == "/" and amount >= 2 and op in (">", ">=") and type(bound.constant) is int and (bound.constant >= 0 if op == ">" else bound.constant >= 1):
            factor = Cost.parameter(initial.parameter, True) if initial.parameter else Cost()
            finding.iterations = "logarithmic in %s (integer division by %d, threshold %s)" % (initial.parameter or initial.constant, amount, bound.constant)
            finding.pattern = "logarithmic shrinkage"
        if factor is None:
            return reject("Unable to determine: update direction, starting sign, or threshold does not establish a supported terminating recurrence.")
        if not initial.parameter and not bound.parameter:
            finding.pattern = "fixed bound"
        finding.reason = "Counter %s has one unconditional '%s %s' update and an invariant bound. " % (name, update.op, amount)
        finding.reason += "Body cost is multiplied by this iteration upper bound; literal bounds remain constants."
        body_env = dict(env)
        # Values modified by a prior iteration cannot be treated as constants.
        # An inner counter must be reset in the body before its loop is analyzed.
        for written_name, _ in writes:
            body_env[written_name] = UNKNOWN
        body, _ = self.statements(node.body.statements, body_env, depth)
        cost = factor.times(body)
        finding.time = cost.notation()
        return cost


def analyze_complexity(result):
    return Analyzer(result).analyze()
