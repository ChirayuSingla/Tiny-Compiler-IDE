import unittest

from tiny_compiler.diagnostics import TinyRuntimeError
from tiny_compiler.ir import BIN, Const, format_ir, interpret_tac
from tiny_compiler.runtime import InputReader
from tests.helpers import compile_source


def tac(src):
    res = compile_source(src)
    assert res.ir is not None, [d.message for d in res.diagnostics.errors]
    return res.ir


def lines(src):
    return [ln.strip() for ln in format_ir(tac(src)).splitlines()]


class ArithmeticIRTests(unittest.TestCase):
    def test_simple_assignment(self):
        self.assertEqual(lines("var x: int = 5;"), ["x = 5", "halt"])

    def test_default_initial_values(self):
        self.assertEqual(lines("var a: int; var b: bool;"), ["a = 0", "b = false", "halt"])

    def test_precedence_is_reflected_in_temporaries(self):
        self.assertEqual(lines("var r: int = 1 + 2 * 3;"),
                         ["$t1 = 2 * 3", "$t2 = 1 + $t1", "r = $t2", "halt"])

    def test_parentheses(self):
        self.assertEqual(lines("var r: int = (1 + 2) * 3;"),
                         ["$t1 = 1 + 2", "$t2 = $t1 * 3", "r = $t2", "halt"])

    def test_left_associativity(self):
        self.assertEqual(lines("var r: int = 10 - 4 - 3;"),
                         ["$t1 = 10 - 4", "$t2 = $t1 - 3", "r = $t2", "halt"])

    def test_variables_and_unary_minus(self):
        self.assertEqual(lines("var a: int = 2; var b: int = -a * 3;"),
                         ["a = 2", "$t1 = - a", "$t2 = $t1 * 3", "b = $t2", "halt"])

    def test_comparison_and_not(self):
        self.assertEqual(lines("var a: int = 1; var b: bool = not (a < 2);"),
                         ["a = 1", "$t1 = a < 2", "$t2 = not $t1", "b = $t2", "halt"])

    def test_io_statements(self):
        self.assertEqual(lines('var n: int; read n; write "n=", n;'),
                         ["n = 0", "read n", 'write "n="', "write ' '", "write n", "newline",
                          "halt"])

    def test_instruction_fields(self):
        ins = tac("var r: int = 1 + 2;")[0]
        self.assertEqual((ins.op, ins.dst, ins.a, ins.b, ins.bin_op),
                         (BIN, "$t1", Const(1), Const(2), "+"))

    def test_const_distinguishes_bool_and_int(self):
        self.assertNotEqual(Const(1), Const(True))
        self.assertEqual(str(Const(True)), "true")
        self.assertEqual(str(Const(7)), "7")


class ControlFlowIRTests(unittest.TestCase):
    def test_if_without_else(self):
        self.assertEqual(
            lines("var x: int = 1; if (x < 2) { x = 5; }"),
            ["x = 1", "$t1 = x < 2", "ifFalse $t1 goto L1", "x = 5", "L1:", "halt"])

    def test_if_else(self):
        self.assertEqual(
            lines("var x: int = 1; if (x < 2) { x = 5; } else { x = 6; }"),
            ["x = 1", "$t1 = x < 2", "ifFalse $t1 goto L1", "x = 5", "goto L2",
             "L1:", "x = 6", "L2:", "halt"])

    def test_while_loop(self):
        self.assertEqual(
            lines("var i: int = 0; while (i < 3) { i = i + 1; }"),
            ["i = 0", "L1:", "$t1 = i < 3", "ifFalse $t1 goto L2", "$t2 = i + 1",
             "i = $t2", "goto L1", "L2:", "halt"])

    def test_else_if_chain_uses_distinct_labels(self):
        text = lines("var a: int = 1; if (a == 1) { a = 2; } else if (a == 2) { a = 3; } "
                     "else { a = 4; }")
        labels = [t for t in text if t.endswith(":")]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(labels), 4)

    def test_and_is_short_circuit(self):
        self.assertEqual(
            lines("var a: bool = true; var b: bool = false; var c: bool = a and b;"),
            ["a = true", "b = false", "$t1 = a", "ifFalse $t1 goto L1", "$t1 = b", "L1:",
             "c = $t1", "halt"])

    def test_or_is_short_circuit(self):
        self.assertEqual(
            lines("var a: bool = true; var b: bool = false; var c: bool = a or b;"),
            ["a = true", "b = false", "$t1 = a", "ifTrue $t1 goto L1", "$t1 = b", "L1:",
             "c = $t1", "halt"])

    def test_every_jump_target_exists(self):
        code = tac("var i: int = 0; while (i < 3) { if (i == 1 or i == 2) { i = i + 1; } "
                   "else { i = i + 2; } }")
        labels = {i.dst for i in code if i.op == "LABEL"}
        jumps = [i for i in code if i.op in ("GOTO", "IFFALSE", "IFTRUE")]
        self.assertGreaterEqual(len(jumps), 4)
        for i in jumps:
            self.assertIn(i.dst, labels)

    def test_program_ends_with_halt(self):
        self.assertEqual(tac("")[-1].op, "HALT")

    def test_shadowed_variables_use_distinct_storage(self):
        text = lines("var x: int = 1; { var x: int = 2; write x; } write x;")
        self.assertIn("x#1 = 2", text)
        self.assertIn("write x#1", text)
        self.assertIn("write x", text)


class InterpreterTests(unittest.TestCase):
    def run_tac(self, src, inp=None):
        return interpret_tac(tac(src), InputReader(inp)).getvalue()

    def test_arithmetic(self):
        self.assertEqual(self.run_tac("write 1 + 2 * 3, (1 + 2) * 3;"), "7 9\n")

    def test_loop(self):
        self.assertEqual(
            self.run_tac("var i: int = 0; var s: int = 0; "
                         "while (i < 4) { s = s + i; i = i + 1; } write s;"), "6\n")

    def test_short_circuit_avoids_division_by_zero(self):
        self.assertEqual(
            self.run_tac("var z: int = 0; if (z != 0 and 5 / z > 1) { write 1; } "
                         "else { write 2; }"), "2\n")

    def test_runtime_division_by_zero(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            self.run_tac("var z: int; read z; write 5 / z;", ["0"])
        self.assertIn("division by zero", cm.exception.message)

    def test_step_limit(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            interpret_tac(tac("while (true) { }"), max_steps=100)
        self.assertIn("100 steps", cm.exception.message)


if __name__ == "__main__":
    unittest.main()
