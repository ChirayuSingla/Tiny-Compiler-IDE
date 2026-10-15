import io
import random
import unittest

from tiny_compiler.codegen import VMInstr, format_code, generate_code
from tiny_compiler.diagnostics import TinyRuntimeError
from tiny_compiler.runtime import InputReader, int_div, int_mod
from tiny_compiler.vm import VM
from tests.helpers import compile_source


def code_of(src):
    res = compile_source(src)
    assert res.code is not None, [d.message for d in res.diagnostics.errors]
    return res.code


def listing(src):
    return [ln.split(None, 1)[1] for ln in format_code(code_of(src)).splitlines()]


def run(src, inp=None, **kw):
    return VM(code_of(src), InputReader(inp), **kw).run().getvalue()


class CodeGenerationTests(unittest.TestCase):
    def test_constant_assignment(self):
        self.assertEqual(listing("var x: int = 5;"), ["PUSH 5", "STORE x", "HALT"])

    def test_expression_is_postfix(self):
        self.assertEqual(
            listing("var r: int = 1 + 2 * 3;"),
            ["PUSH 2", "PUSH 3", "MUL", "STORE $t1", "PUSH 1", "LOAD $t1", "ADD",
             "STORE $t2", "LOAD $t2", "STORE r", "HALT"])

    def test_every_binary_operator_has_an_instruction(self):
        ops = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
               "<": "LT", "<=": "LE", ">": "GT", ">=": "GE", "==": "EQ", "!=": "NE"}
        for sym, name in ops.items():
            self.assertIn(name, listing("var a: int = 6; var b: int = 3; write a %s b;" % sym))

    def test_unary_instructions(self):
        self.assertIn("NEG", listing("var a: int = 1; write -a;"))
        self.assertIn("NOT", listing("var a: bool = true; write not a;"))

    def test_bool_constants_use_push(self):
        self.assertEqual(listing("var b: bool = true;")[0], "PUSH true")

    def test_jump_targets_are_instruction_indexes(self):
        code = code_of("var i: int = 0; while (i < 2) { i = i + 1; }")
        for idx, ins in enumerate(code):
            if ins.op in ("JMP", "JZ", "JNZ"):
                self.assertIsInstance(ins.arg, int)
                self.assertTrue(0 <= ins.arg <= len(code))
        # the loop's back-edge jumps to the first instruction of the condition
        jmp = [i for i in code if i.op == "JMP"][0]
        self.assertEqual(code[jmp.arg].op, "LOAD")
        self.assertEqual(code[jmp.arg].arg, "i")

    def test_if_else_jumps(self):
        text = listing("var x: int = 1; if (x < 2) { x = 5; } else { x = 6; }")
        self.assertEqual(text, [
            "PUSH 1", "STORE x",                                   # 0-1
            "LOAD x", "PUSH 2", "LT", "STORE $t1",                 # 2-5
            "LOAD $t1", "JZ 11",                                   # 6-7  else -> 11
            "PUSH 5", "STORE x", "JMP 13",                         # 8-10 then, skip else
            "PUSH 6", "STORE x",                                   # 11-12 else
            "HALT"])                                               # 13

    def test_io_instructions(self):
        text = listing('var n: int; var b: bool; read n; read b; write "hi", n;')
        for expected in ("READ_INT n", "READ_BOOL b", 'PRINT_STR "hi"', "PRINT_SPACE",
                         "PRINT", "PRINT_NL"):
            self.assertIn(expected, text)

    def test_listing_format(self):
        self.assertEqual(format_code([VMInstr("PUSH", 1), VMInstr("HALT")]),
                         "0000  PUSH 1\n0001  HALT")

    def test_generate_code_resolves_forward_label_at_end(self):
        res = compile_source("var x: int = 1; if (x < 2) { x = 3; }")
        code = generate_code(res.ir)
        jz = [i for i in code if i.op == "JZ"][0]
        self.assertEqual(code[jz.arg].op, "HALT")


class ExecutionTests(unittest.TestCase):
    def test_arithmetic_results(self):
        self.assertEqual(run("write 1 + 2 * 3, (1 + 2) * 3, 10 - 4 - 3, 2 * (3 + 4) * 5;"),
                         "7 9 3 70\n")

    def test_integer_division_truncates_toward_zero(self):
        self.assertEqual(run("write 7 / 2, -7 / 2, 7 / -2, -7 / -2;"), "3 -3 -3 3\n")

    def test_modulo_has_sign_of_dividend(self):
        self.assertEqual(run("write 7 % 3, -7 % 3, 7 % -3, -7 % -3;"), "1 -1 1 -1\n")

    def test_division_identity(self):
        for a in (-9, -7, -1, 0, 1, 7, 9):
            for b in (-4, -3, -1, 1, 3, 4):
                self.assertEqual(int_div(a, b) * b + int_mod(a, b), a)

    def test_comparisons_and_bool_printing(self):
        self.assertEqual(run("write 1 < 2, 2 <= 2, 3 > 4, 4 >= 5, 1 == 1, 1 != 1;"),
                         "true true false false true false\n")

    def test_logic_operators(self):
        self.assertEqual(run("write true and false, true or false, not true, not false;"),
                         "false true false true\n")

    def test_big_integers_do_not_overflow(self):
        self.assertEqual(run("var x: int = 99999999999; write x * x;"),
                         "9999999999800000000001\n")

    def test_while_loop_accumulates(self):
        self.assertEqual(
            run("var i: int = 1; var p: int = 1; while (i <= 5) { p = p * i; i = i + 1; } "
                "write p;"), "120\n")

    def test_if_else_branches(self):
        src = "var n: int; read n; if (n > 0) { write 1; } else if (n < 0) { write -1; } " \
              "else { write 0; }"
        self.assertEqual([run(src, [v]) for v in ("5", "-5", "0")], ["1\n", "-1\n", "0\n"])

    def test_declaration_inside_loop_is_reinitialised_each_iteration(self):
        src = "var i: int = 0; while (i < 3) { var t: int; t = t + 1; write t; i = i + 1; }"
        self.assertEqual(run(src), "1\n1\n1\n")

    def test_uninitialised_variables_default_to_zero_and_false(self):
        self.assertEqual(run("var n: int; var b: bool; write n, b;"), "0 false\n")

    def test_shadowing_at_runtime(self):
        self.assertEqual(
            run("var x: int = 1; { var x: int = 2; x = x + 1; write x; } write x;"), "3\n1\n")

    def test_string_escapes_in_output(self):
        self.assertEqual(run(r'write "a\tb", "q\"";'), 'a\tb q"\n')

    def test_empty_program_prints_nothing(self):
        self.assertEqual(run(""), "")

    def test_stack_is_empty_after_run(self):
        vm = VM(code_of("var x: int = 1 + 2 * 3; write x;"), InputReader([]))
        vm.run()
        self.assertEqual(vm.stack, [])
        self.assertEqual(vm.memory["x"], 7)


class InputTests(unittest.TestCase):
    def test_read_int_and_bool(self):
        self.assertEqual(run("var n: int; var b: bool; read n; read b; write n, b;",
                             ["42 true"]), "42 true\n")

    def test_values_may_span_lines_and_be_negative(self):
        self.assertEqual(run("var a: int; var b: int; read a; read b; write a + b;",
                             ["-5", "", "  8  "]), "3\n")

    def test_byte_order_mark_at_start_of_input_is_ignored(self):
        self.assertEqual(run("var n: int; read n; write n;", ["﻿7"]), "7\n")

    def test_end_of_input_is_a_runtime_error(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("var n: int; read n; read n;", ["1"])
        self.assertIn("no more input available for 'read n'", cm.exception.message)

    def test_invalid_integer_input(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("var n: int; read n;", ["abc"])
        self.assertIn("invalid integer input 'abc'", cm.exception.message)

    def test_invalid_bool_input(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("var b: bool; read b;", ["maybe"])
        self.assertIn("invalid bool input", cm.exception.message)

    def test_float_is_not_valid_integer_input(self):
        with self.assertRaises(TinyRuntimeError):
            run("var n: int; read n;", ["3.5"])

    def test_read_error_reports_source_line(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("var n: int;\n\nread n;", ["x"])
        self.assertEqual(cm.exception.line, 3)


class RuntimeErrorTests(unittest.TestCase):
    def test_division_by_zero_at_runtime(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("var z: int; read z; write 10 / z;", ["0"])
        self.assertEqual(cm.exception.message, "division by zero")

    def test_modulo_by_zero_at_runtime_reports_line(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("var z: int;\nwrite 10 % z;")
        self.assertEqual((cm.exception.message, cm.exception.line), ("modulo by zero", 2))

    def test_output_before_error_is_kept(self):
        vm = VM(code_of('var z: int; write "before"; write 1 / z;'), InputReader([]))
        with self.assertRaises(TinyRuntimeError):
            vm.run()
        self.assertEqual(vm.out.getvalue(), "before\n")

    def test_infinite_loop_is_stopped(self):
        with self.assertRaises(TinyRuntimeError) as cm:
            run("while (true) { }", max_steps=1000)
        self.assertIn("1000 steps", cm.exception.message)

    def test_trace_output(self):
        buf = io.StringIO()
        run("var x: int = 1 + 2;", trace=buf)
        lines = buf.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("0000  PUSH 1"))
        self.assertIn("stack=[]", lines[0])
        self.assertIn("stack=['1', '2']", lines[2])


# --- reference-model (differential) test ------------------------------------
def _gen_expr(rng, depth):
    """Random int expression; returns (source, python value)."""
    if depth == 0 or rng.random() < 0.25:
        v = rng.randint(0, 20)
        return str(v), v
    kind = rng.choice(["+", "-", "*", "/", "%", "neg", "paren"])
    if kind == "neg":
        s, v = _gen_expr(rng, depth - 1)
        return "-(%s)" % s, -v
    if kind == "paren":
        s, v = _gen_expr(rng, depth - 1)
        return "(%s)" % s, v
    ls, lv = _gen_expr(rng, depth - 1)
    rs, rv = _gen_expr(rng, depth - 1)
    if kind in "/%" and rv == 0:
        kind = "+"
    if kind == "+":
        return "%s + (%s)" % (ls, rs), lv + rv
    if kind == "-":
        return "%s - (%s)" % (ls, rs), lv - rv
    if kind == "*":
        return "(%s) * (%s)" % (ls, rs), lv * rv
    if kind == "/":
        return "(%s) / (%s)" % (ls, rs), int_div(lv, rv)
    return "(%s) %% (%s)" % (ls, rs), int_mod(lv, rv)


class DifferentialTests(unittest.TestCase):
    def test_random_expressions_match_python_reference(self):
        rng = random.Random(20260101)
        # constant divisors that evaluate to 0 are rejected at compile time,
        # so keep only expressions the generator proved non-zero.
        checked = 0
        for _ in range(300):
            src, expected = _gen_expr(rng, 4)
            program = "write %s;" % src
            res = compile_source(program)
            if not res.ok:  # e.g. a non-literal divisor folded to 0 by eval_const
                continue
            got = VM(res.code, InputReader([])).run().getvalue()
            self.assertEqual(got, "%d\n" % expected, program)
            checked += 1
        self.assertGreater(checked, 200)


if __name__ == "__main__":
    unittest.main()
