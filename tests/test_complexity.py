import unittest

from tiny_compiler.complexity import analyze_complexity
from tiny_compiler.pipeline import compile_source


def estimate(source):
    result = compile_source(source)
    if not result.ok:
        raise AssertionError(repr(result.diagnostics.errors))
    return analyze_complexity(result)


INPUT = "var n: int; read n; "


class ComplexityTests(unittest.TestCase):
    def test_constant_time_and_scalar_space(self):
        report = estimate("var x: int = 2; var b: bool = true; if (b) { write x * 3; }")
        self.assertEqual(report.time, "O(1)")
        self.assertEqual(report.auxiliary_space, "O(1) scalar slots")
        self.assertEqual(report.declared_slots, 2)
        self.assertGreater(report.temporary_slots, 0)
        self.assertIn("not exact", report.text())
        self.assertIn("arbitrary precision", report.text())

    def test_linear_increasing_and_decreasing(self):
        for source in (INPUT + "var i: int = 0; while (i < n) { i = i + 1; }",
                       INPUT + "var i: int = 1; while (i <= n) { i = i + 2; }",
                       INPUT + "var i: int = 0; while (n > i) { i = i + 1; }",
                       INPUT + "while (n > 0) { n = n - 1; }"):
            with self.subTest(source=source):
                report = estimate(source)
                self.assertEqual(report.time, "O(n)")
                self.assertEqual(report.auxiliary_space, "O(1) scalar slots")
                self.assertIn("ceil", report.loops[0].iterations)

    def test_nested_independent_loops_and_reset_detection(self):
        source = INPUT + "var i: int = 0; while (i < n) { var j: int = 0; while (j < n) { j = j + 1; } i = i + 1; }"
        report = estimate(source)
        self.assertEqual(report.time, "O(n^2)")
        self.assertEqual([finding.depth for finding in report.loops], [1, 2])
        outside = INPUT + "var j: int = 0; var i: int = 0; while (i < n) { while (j < n) { j = j + 1; } i = i + 1; }"
        self.assertEqual(estimate(outside).time, "Unable to determine")

    def test_distinct_nested_parameters(self):
        report = estimate(INPUT + "var m: int; read m; var i: int = 0; while (i < n) { var j: int = 0; while (j < m) { j = j + 1; } i = i + 1; }")
        self.assertEqual(report.time, "O(m * n)")

    def test_logarithmic_growth_and_shrinkage(self):
        for source in (INPUT + "var i: int = 1; while (i < n) { i = i * 2; }",
                       INPUT + "while (n > 0) { n = n / 2; }",
                       INPUT + "while (n >= 1) { n = n / 10; }"):
            with self.subTest(source=source):
                self.assertEqual(estimate(source).time, "O(log n)")

    def test_linear_times_logarithmic_nested_loop(self):
        report = estimate(INPUT + "var i: int = 0; while (i < n) { var j: int = 1; while (j < n) { j = j * 2; } i = i + 1; }")
        self.assertEqual(report.time, "O(n * log n)")

    def test_literal_bounds_are_constant_wrt_runtime_inputs(self):
        report = estimate("var i: int = 0; while (i < 100) { i = i + 1; }")
        self.assertEqual(report.time, "O(1)")
        self.assertEqual(report.loops[0].pattern, "fixed bound")

    def test_ambiguous_and_nonterminating_patterns_are_not_guessed(self):
        programs = [
            INPUT + "var i: int = 0; while (i < n) { if (n > 2) { i = i + 1; } }",
            INPUT + "var i: int = 0; while (i < n) { n = n - 1; i = i + 1; }",
            INPUT + "var i: int = 0; while (i < n) { i = i + 1; i = i + 1; }",
            INPUT + "var i: int = 0; while (i < n) { i = i * 2; }",
            INPUT + "var i: int = 0; while (i < n) { i = i - 1; }",
            INPUT + "while (n >= 0) { n = n / 2; }",
            INPUT + "while (n != 0) { n = n - 1; }",
            "while (true) {}",
        ]
        for source in programs:
            with self.subTest(source=source):
                report = estimate(source)
                self.assertEqual(report.time, "Unable to determine")
                self.assertEqual(report.auxiliary_space, "O(1) scalar slots")
                self.assertTrue(any("Unable to determine" in finding.reason for finding in report.loops))

    def test_dependent_nested_bound_and_variable_step_are_rejected(self):
        source = INPUT + "var i: int = 0; while (i < n) { var j: int = 0; while (j < i) { j = j + 1; } i = i + 1; }"
        self.assertEqual(estimate(source).time, "Unable to determine")
        variable_step = INPUT + "var step: int = 1; var i: int = 0; while (i < n) { i = i + step; }"
        self.assertEqual(estimate(variable_step).time, "Unable to determine")

    def test_branch_dataflow_and_input_alias(self):
        report = estimate(INPUT + "var limit: int = n; var i: int = 0; while (i < limit) { n = n - 1; i = i + 1; }")
        self.assertEqual(report.time, "O(n)")
        branch = INPUT + "var b: bool; read b; var i: int; if (b) { i = 0; } else { i = 0; } while (i < n) { i = i + 1; }"
        self.assertEqual(estimate(branch).time, "O(n)")

    def test_unreachable_loop_and_literal_condition_are_handled(self):
        self.assertEqual(estimate("while (false) { while (true) {} }").time, "O(1)")
        self.assertEqual(estimate("if (false) { while (true) {} } write 1;").time, "O(1)")

    def test_sequential_costs_and_shadowing_use_symbol_identity(self):
        sequential = INPUT + "var i: int = 0; while (i < n) { i = i + 1; } i = 1; while (i < n) { i = i * 2; }"
        self.assertEqual(estimate(sequential).time, "O(n)")
        shadowing = INPUT + "var i: int = 0; while (i < n) { { var i: int = 0; while (i < n) { i = i + 1; } } i = i + 1; }"
        self.assertEqual(estimate(shadowing).time, "O(n^2)")

    def test_compile_errors_have_no_complexity_claim(self):
        report = analyze_complexity(compile_source("write missing;"))
        self.assertEqual(report.time, "Unable to determine")
        self.assertEqual(report.auxiliary_space, "Unable to determine")
        self.assertEqual(report.confidence, "Unavailable")

    def test_runtime_measurements_do_not_feed_static_estimate(self):
        from tiny_compiler.vm import VM
        from tiny_compiler.runtime import InputReader
        result = compile_source(INPUT + "var i: int = 0; while (i < n) { i = i + 1; } write i;")
        first = analyze_complexity(result)
        machines = [VM(result.code, InputReader([str(n)])) for n in (2, 20)]
        for machine in machines:
            machine.run()
        self.assertLess(machines[0].steps, machines[1].steps)
        self.assertEqual(first.time, analyze_complexity(result).time)
        self.assertEqual(first.time, "O(n)")
