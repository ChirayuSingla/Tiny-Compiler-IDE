import unittest

from tiny_compiler.diagnostics import DiagnosticBag
from tiny_compiler.semantic import analyze, eval_const
from tiny_compiler.symbol_table import format_symbols
from tests.helpers import compile_errors, parse_ok


def check(src):
    """Analyse `src`; return (program, table, bag)."""
    prog = parse_ok(src)
    bag = DiagnosticBag()
    table = analyze(prog, bag)
    return prog, table, bag


def errs(src):
    _, _, bag = check(src)
    return [d.message for d in bag.errors]


class DeclarationTests(unittest.TestCase):
    def test_valid_program_has_no_errors(self):
        self.assertEqual(errs("var x: int = 1; x = x + 1; write x;"), [])

    def test_undeclared_variable_in_expression(self):
        e = errs("var x: int = y;")
        self.assertEqual(len(e), 1)
        self.assertIn("variable 'y' is not declared", e[0])

    def test_undeclared_variable_in_assignment_and_read(self):
        e = errs("a = 1; read b;")
        self.assertEqual(len(e), 2)
        self.assertIn("'a'", e[0])
        self.assertIn("'b'", e[1])

    def test_duplicate_declaration_same_scope(self):
        e = errs("var x: int; var x: bool;")
        self.assertEqual(len(e), 1)
        self.assertIn("already declared in this scope", e[0])
        self.assertIn("line 1:5", e[0])

    def test_use_before_declaration_is_distinguished_from_undeclared(self):
        e = errs("x = 1; var x: int;")
        self.assertEqual(len(e), 1)
        self.assertIn("used before its declaration", e[0])
        self.assertIn("line 1", e[0])

    def test_self_reference_in_initialiser(self):
        e = errs("var x: int = x + 1;")
        self.assertEqual(len(e), 1)
        self.assertIn("used before its declaration", e[0])

    def test_declaration_visible_after_it(self):
        self.assertEqual(errs("var x: int; var y: int = x;"), [])


class ScopeTests(unittest.TestCase):
    def test_inner_scope_variable_not_visible_outside(self):
        e = errs("{ var t: int = 1; } t = 2;")
        self.assertEqual(len(e), 1)
        self.assertIn("'t' is not declared", e[0])

    def test_shadowing_is_allowed_and_gets_distinct_storage(self):
        prog, table, bag = check("var x: int = 1; { var x: int = 2; x = 3; } x = 4;")
        self.assertFalse(bag.has_errors())
        self.assertEqual([s.unique for s in table.all_symbols], ["x", "x#1"])
        inner_assign = prog.statements[1].statements[1]
        outer_assign = prog.statements[2]
        self.assertEqual(inner_assign.symbol.unique, "x#1")
        self.assertEqual(outer_assign.symbol.unique, "x")

    def test_same_name_in_sibling_blocks_is_allowed(self):
        self.assertEqual(errs("{ var a: int; a = 1; } { var a: int; a = 2; }"), [])

    def test_outer_variable_visible_in_nested_blocks(self):
        self.assertEqual(
            errs("var n: int = 3; while (n > 0) { if (n == 1) { n = 0; } else { n = n - 1; } }"),
            [])

    def test_late_inner_declaration_hides_outer_variable_before_it(self):
        e = errs("var x: int = 1; { write x; var x: int = 2; }")
        self.assertEqual(len(e), 1)
        self.assertIn("used before its declaration", e[0])

    def test_duplicate_in_inner_block(self):
        e = errs("{ var a: int; var a: int; }")
        self.assertEqual(len(e), 1)

    def test_scope_depths_in_symbol_table(self):
        _, table, _ = check("var a: int; { var b: int; { var c: bool; } }")
        self.assertEqual([(s.name, s.depth) for s in table.all_symbols],
                         [("a", 0), ("b", 1), ("c", 2)])


class TypeTests(unittest.TestCase):
    def test_initialiser_type_mismatch(self):
        e = errs("var f: bool = 1;")
        self.assertEqual(len(e), 1)
        self.assertIn("cannot initialise 'bool' variable 'f'", e[0])

    def test_assignment_type_mismatch_both_directions(self):
        e = errs("var i: int; var b: bool; i = true; b = 3;")
        self.assertEqual(len(e), 2)
        self.assertIn("'bool' to 'int'", e[0])
        self.assertIn("'int' to 'bool'", e[1])

    def test_arithmetic_requires_ints(self):
        for src in ["write 1 + true;", "write true * 2;", "write true - false;",
                    "write 1 / true;", "write 1 % false;"]:
            e = errs(src)
            self.assertEqual(len(e), 1, src)
            self.assertIn("needs two 'int' operands", e[0])

    def test_unary_minus_requires_int(self):
        e = errs("write -true;")
        self.assertIn("unary '-' needs an 'int'", e[0])

    def test_not_requires_bool(self):
        e = errs("write not 3;")
        self.assertIn("'not' needs a 'bool'", e[0])

    def test_logical_operators_require_bools(self):
        e = errs("write 1 and 2; write true or 0;")
        self.assertEqual(len(e), 2)
        self.assertIn("needs two 'bool' operands", e[0])

    def test_ordering_requires_ints(self):
        e = errs("write true < false;")
        self.assertIn("needs two 'int' operands", e[0])

    def test_equality_requires_same_types(self):
        self.assertEqual(errs("write 1 == 2; write true != false;"), [])
        e = errs("write 1 == true;")
        self.assertIn("cannot compare 'int' with 'bool'", e[0])

    def test_conditions_must_be_bool(self):
        e = errs("var n: int = 1; if (n) { } while (n + 1) { }")
        self.assertEqual(len(e), 2)
        self.assertIn("condition of 'if' must be of type 'bool'", e[0])
        self.assertIn("condition of 'while'", e[1])

    def test_comparison_result_is_bool(self):
        self.assertEqual(errs("var b: bool = 1 < 2; if (b) { } while (1 < 2 and b) { }"), [])

    def test_expression_types_are_annotated(self):
        prog, _, _ = check("var b: bool = 1 + 2 < 4;")
        init = prog.statements[0].init
        self.assertEqual(init.type, "bool")
        self.assertEqual(init.left.type, "int")

    def test_errors_do_not_cascade(self):
        # one undeclared name must not produce extra type errors around it
        e = errs("var x: int = q + 1;")
        self.assertEqual(len(e), 1)


class DivisionByZeroTests(unittest.TestCase):
    def test_literal_zero_divisor(self):
        e = errs("write 5 / 0;")
        self.assertEqual(len(e), 1)
        self.assertIn("division by zero", e[0])

    def test_constant_expression_divisor(self):
        self.assertIn("division by zero", errs("write 5 % (3 - 3);")[0])
        self.assertIn("division by zero", errs("write 5 / (2 * 0);")[0])

    def test_non_constant_divisor_is_allowed_at_compile_time(self):
        self.assertEqual(errs("var z: int = 0; write 5 / z;"), [])

    def test_nonzero_constant_divisor_ok(self):
        self.assertEqual(errs("write 5 / (3 - 1);"), [])

    def test_eval_const(self):
        e = parse_ok("x = 2 + 3 * 4;").statements[0].value
        self.assertEqual(eval_const(e), 14)
        e = parse_ok("x = -(7 / 2);").statements[0].value
        self.assertEqual(eval_const(e), -3)
        e = parse_ok("x = y + 1;").statements[0].value
        self.assertIsNone(eval_const(e))


class WarningAndSymbolTableTests(unittest.TestCase):
    def test_unused_variable_warning(self):
        _, _, bag = check("var unused: int = 3; var used: int = 1; write used;")
        self.assertFalse(bag.has_errors())
        self.assertEqual(len(bag.warnings), 1)
        self.assertIn("'unused'", bag.warnings[0].message)

    def test_no_warnings_when_there_are_errors(self):
        _, _, bag = check("var unused: int = true;")
        self.assertTrue(bag.has_errors())
        self.assertEqual(bag.warnings, [])

    def test_symbol_table_report(self):
        _, table, _ = check("var a: int = 1; var b: bool; write a;")
        rows = format_symbols(table).splitlines()
        self.assertIn("int", rows[1])
        self.assertIn("bool", rows[2])
        self.assertTrue(rows[1].rstrip().endswith("yes"))
        self.assertTrue(rows[2].rstrip().endswith("no"))

    def test_symbol_positions_recorded(self):
        _, table, _ = check("\n  var q: int;")
        self.assertEqual((table.all_symbols[0].line, table.all_symbols[0].col), (2, 7))


class DiagnosticPositionTests(unittest.TestCase):
    def test_error_positions(self):
        res, _ = compile_errors("var x: int = 1;\nvar x: int = 2;\n  y = 3;")
        pos = [(d.line, d.col) for d in res.diagnostics.errors]
        self.assertEqual(pos, [(2, 5), (3, 3)])

    def test_caret_rendering(self):
        res, _ = compile_errors("write 1 + true;")
        text = res.diagnostics.errors[0].format(res.source, "t.tiny")
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("t.tiny:1:9: semantic error:"))
        self.assertEqual(lines[1], "    1 | write 1 + true;")
        self.assertEqual(lines[2], "      |         ^")


if __name__ == "__main__":
    unittest.main()
