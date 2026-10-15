import unittest

from tiny_compiler import ast_nodes as A
from tiny_compiler.ast_nodes import format_ast
from tests.helpers import expr_of, messages, parse_ok, parse_source


class PrecedenceTests(unittest.TestCase):
    def test_multiplication_binds_tighter_than_addition(self):
        self.assertEqual(expr_of("1 + 2 * 3"), "(+ 1 (* 2 3))")
        self.assertEqual(expr_of("1 * 2 + 3"), "(+ (* 1 2) 3)")

    def test_subtraction_is_left_associative(self):
        self.assertEqual(expr_of("10 - 4 - 3"), "(- (- 10 4) 3)")

    def test_division_and_modulo_are_left_associative(self):
        self.assertEqual(expr_of("100 / 5 / 2"), "(/ (/ 100 5) 2)")
        self.assertEqual(expr_of("a * b % c"), "(% (* a b) c)")

    def test_parentheses_override_precedence(self):
        self.assertEqual(expr_of("(1 + 2) * 3"), "(* (+ 1 2) 3)")
        self.assertEqual(expr_of("2 * (3 + 4) * 5"), "(* (* 2 (+ 3 4)) 5)")
        self.assertEqual(expr_of("((7))"), "7")

    def test_unary_minus(self):
        self.assertEqual(expr_of("-x"), "(- x)")
        self.assertEqual(expr_of("- - 3"), "(- (- 3))")
        self.assertEqual(expr_of("-a * b"), "(* (- a) b)")
        self.assertEqual(expr_of("2 - -3"), "(- 2 (- 3))")

    def test_comparison_is_below_arithmetic(self):
        self.assertEqual(expr_of("a + 1 < b * 2"), "(< (+ a 1) (* b 2))")
        self.assertEqual(expr_of("a == b"), "(== a b)")
        self.assertEqual(expr_of("a >= 1"), "(>= a 1)")

    def test_logical_operator_precedence_not_and_or(self):
        self.assertEqual(expr_of("a or b and c"), "(or a (and b c))")
        self.assertEqual(expr_of("not a and b"), "(and (not a) b)")
        self.assertEqual(expr_of("not a < b"), "(not (< a b))")
        self.assertEqual(expr_of("a < b and c < d or e"), "(or (and (< a b) (< c d)) e)")

    def test_or_and_are_left_associative(self):
        self.assertEqual(expr_of("a or b or c"), "(or (or a b) c)")
        self.assertEqual(expr_of("a and b and c"), "(and (and a b) c)")

    def test_chained_comparison_is_a_syntax_error(self):
        _, bag = parse_source("x = 1 < 2 < 3;")
        self.assertEqual(len(bag.errors), 1)
        self.assertIn("cannot be chained", bag.errors[0].message)


class StatementShapeTests(unittest.TestCase):
    def test_empty_program(self):
        self.assertEqual(parse_ok("").statements, [])
        self.assertEqual(parse_ok("// just a comment\n").statements, [])

    def test_var_declaration_forms(self):
        prog = parse_ok("var a: int; var b: bool = true; var c: int = 1 + 2;")
        a, b, c = prog.statements
        self.assertEqual((a.name, a.type_name, a.init), ("a", "int", None))
        self.assertEqual((b.name, b.type_name), ("b", "bool"))
        self.assertIsInstance(b.init, A.BoolLit)
        self.assertIsInstance(c.init, A.Binary)

    def test_assignment(self):
        st = parse_ok("x = y + 1;").statements[0]
        self.assertIsInstance(st, A.Assign)
        self.assertEqual(st.name, "x")

    def test_if_without_else(self):
        st = parse_ok("if (a < b) { x = 1; }").statements[0]
        self.assertIsInstance(st, A.If)
        self.assertIsNone(st.else_branch)
        self.assertEqual(len(st.then_block.statements), 1)

    def test_if_else(self):
        st = parse_ok("if (a) { x = 1; } else { x = 2; }").statements[0]
        self.assertIsInstance(st.else_branch, A.Block)

    def test_else_if_chain_nests_if_nodes(self):
        st = parse_ok("if (a) { } else if (b) { } else { }").statements[0]
        self.assertIsInstance(st.else_branch, A.If)
        self.assertIsInstance(st.else_branch.else_branch, A.Block)

    def test_while(self):
        st = parse_ok("while (i < 3) { i = i + 1; }").statements[0]
        self.assertIsInstance(st, A.While)
        self.assertEqual(len(st.body.statements), 1)

    def test_read_and_write(self):
        prog = parse_ok('read n; write "n =", n, n * 2;')
        r, w = prog.statements
        self.assertIsInstance(r, A.Read)
        self.assertEqual(r.name, "n")
        self.assertEqual(len(w.items), 3)
        self.assertIsInstance(w.items[0], A.StringLit)
        self.assertIsInstance(w.items[2], A.Binary)

    def test_nested_block_statement(self):
        st = parse_ok("{ { x = 1; } }").statements[0]
        self.assertIsInstance(st, A.Block)
        self.assertIsInstance(st.statements[0], A.Block)

    def test_node_positions(self):
        prog = parse_ok("\n  x = 1 + 2;")
        st = prog.statements[0]
        self.assertEqual((st.line, st.col), (2, 3))
        self.assertEqual((st.value.line, st.value.col), (2, 9))  # position of the '+'

    def test_ast_dump_is_a_tree(self):
        text = format_ast(parse_ok("x = 1 + 2;"))
        self.assertEqual(text.splitlines(),
                         ["Program", "`-- Assign x", "    `-- Binary '+'",
                          "        |-- IntLit 1", "        `-- IntLit 2"])


class SyntaxErrorTests(unittest.TestCase):
    def one_error(self, src):
        _, bag = parse_source(src)
        self.assertEqual(len(bag.errors), 1, messages(bag))
        return bag.errors[0]

    def test_missing_semicolon_points_after_previous_token(self):
        d = self.one_error("x = 5\ny = 6;")
        self.assertIn("expected ';'", d.message)
        self.assertEqual((d.line, d.col), (1, 6))

    def test_missing_semicolon_after_declaration(self):
        d = self.one_error("var x: int")
        self.assertIn("expected ';'", d.message)

    def test_missing_right_paren_in_condition(self):
        d = self.one_error("if (x > 2 { x = 1; }")
        self.assertIn("expected ')'", d.message)

    def test_missing_parentheses_around_condition(self):
        d = self.one_error("while x < 3 { }")
        self.assertIn("expected '(' after 'while'", d.message)

    def test_unclosed_parenthesis_in_expression(self):
        d = self.one_error("x = (1 + 2;")
        self.assertIn("expected ')'", d.message)

    def test_missing_operand(self):
        d = self.one_error("x = 5 + ;")
        self.assertIn("expected an expression", d.message)
        self.assertEqual((d.line, d.col), (1, 8))

    def test_missing_expression_after_equals(self):
        d = self.one_error("x = ;")
        self.assertIn("expected an expression", d.message)

    def test_missing_closing_brace(self):
        d = self.one_error("while (true) { x = 1;")
        self.assertIn("expected '}'", d.message)
        self.assertIn("opened at line 1:14", d.message)

    def test_unmatched_closing_brace(self):
        d = self.one_error("x = 1; }")
        self.assertIn("unexpected '}'", d.message)

    def test_body_must_be_a_block(self):
        d = self.one_error("if (a) x = 1;")
        self.assertIn("expected '{'", d.message)

    def test_else_without_if(self):
        d = self.one_error("else { }")
        self.assertIn("'else' without a matching 'if'", d.message)

    def test_missing_type(self):
        d = self.one_error("var x: = 3;")
        self.assertIn("expected a type", d.message)

    def test_missing_colon_in_declaration(self):
        d = self.one_error("var x int;")
        self.assertIn("expected ':'", d.message)

    def test_missing_name_after_var(self):
        d = self.one_error("var 5;")
        self.assertIn("expected a variable name", d.message)

    def test_assignment_needs_equals(self):
        d = self.one_error("x + 1;")
        self.assertIn("expected '='", d.message)

    def test_string_outside_write_is_rejected(self):
        d = self.one_error('x = "hi";')
        self.assertIn("only appear directly in a 'write'", d.message)

    def test_statement_cannot_start_with_a_number(self):
        d = self.one_error("5 = x;")
        self.assertIn("expected a statement", d.message)

    def test_empty_write(self):
        d = self.one_error("write ;")
        self.assertIn("expected an expression", d.message)


class UnsupportedConstructTests(unittest.TestCase):
    def check(self, src, fragment):
        _, bag = parse_source(src)
        self.assertGreaterEqual(len(bag.errors), 1)
        self.assertIn(fragment, bag.errors[0].message)

    def test_for_loop(self):
        self.check("for (i = 0; i < 3; i = i + 1) { }", "'for' loops are not supported")

    def test_print(self):
        self.check("print x;", "use 'write'")

    def test_function_call(self):
        self.check("x = f(2);", "function calls are not supported")

    def test_float_type(self):
        self.check("var x: float;", "floating-point types are not supported")

    def test_elif(self):
        self.check("if (a) { } elif (b) { }", "'elif'")

    def test_return_and_break(self):
        self.check("return 1;", "'return' is not supported")
        self.check("break;", "'break' is not supported")


class ErrorRecoveryTests(unittest.TestCase):
    def test_several_errors_are_reported_in_one_run(self):
        src = "var a: int = 1\nx = 2 + ;\nwhile a < 3 { }\nwrite a;\n"
        _, bag = parse_source(src)
        lines = [d.line for d in bag.errors]
        self.assertEqual(lines, [1, 2, 3])

    def test_valid_statements_after_an_error_still_parse(self):
        prog, bag = parse_source("x = ;\ny = 2;\nwrite y;")
        self.assertEqual(len(bag.errors), 1)
        kinds = [type(s).__name__ for s in prog.statements]
        self.assertEqual(kinds, ["Assign", "Write"])

    def test_error_inside_block_does_not_leak_out(self):
        src = "while (true) { x = ; y = 1; }\nz = 3;"
        prog, bag = parse_source(src)
        self.assertEqual(len(bag.errors), 1)
        self.assertEqual(type(prog.statements[-1]).__name__, "Assign")

    def test_parser_always_terminates_on_garbage(self):
        for src in ["}}}}", "((((", "var var var", ";;;;", "if if if", "else else", "{ { {"]:
            _, bag = parse_source(src)
            self.assertTrue(bag.has_errors(), src)


if __name__ == "__main__":
    unittest.main()
