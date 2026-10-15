"""End-to-end tests: every example program through the real CLI and the API."""
import os
import subprocess
import sys
import unittest

from tests.helpers import EXAMPLES, ROOT
from tiny_compiler import run_source
from tiny_compiler.diagnostics import CompileError, TinyRuntimeError

VALID = ["hello", "arithmetic", "conditional", "loop", "input_output", "fibonacci",
         "gcd", "scopes", "logic"]
INVALID_COMPILE = ["invalid_character", "invalid_syntax", "invalid_semantics"]


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def example(name, ext):
    return os.path.join(EXAMPLES, name + ext)


def cli(args, stdin_text=""):
    proc = subprocess.run([sys.executable, "main.py"] + args, cwd=ROOT, input=stdin_text,
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout.replace("\r\n", "\n"), proc.stderr.replace("\r\n", "\n")


def input_for(name):
    p = example(name, ".input")
    return read(p) if os.path.exists(p) else ""


class ExampleProgramTests(unittest.TestCase):
    def test_valid_examples_via_cli(self):
        for name in VALID:
            with self.subTest(example=name):
                code, out, err = cli(["examples/%s.tiny" % name], input_for(name))
                self.assertEqual(code, 0, err)
                self.assertEqual(out, read(example(name, ".expected")))

    def test_valid_examples_with_vm_and_tac_backends_via_api(self):
        for name in VALID:
            expected = read(example(name, ".expected"))
            src = read(example(name, ".tiny"))
            lines = input_for(name).splitlines()
            for backend in ("vm", "ir"):
                with self.subTest(example=name, backend=backend):
                    self.assertEqual(run_source(src, lines, backend), expected)

    def test_compile_error_examples_report_expected_diagnostics(self):
        for name in INVALID_COMPILE:
            with self.subTest(example=name):
                code, out, err = cli(["examples/%s.tiny" % name])
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertEqual(err, read(example(name, ".expected")))
                self.assertNotIn("Traceback", err)

    def test_runtime_error_example(self):
        code, out, err = cli(["examples/invalid_runtime.tiny"], input_for("invalid_runtime"))
        self.assertEqual(code, 3)
        self.assertEqual(out, read(example("invalid_runtime", ".expected")))
        self.assertEqual(err, read(example("invalid_runtime", ".expected_err")))

    def test_runtime_error_via_api(self):
        src = read(example("invalid_runtime", ".tiny"))
        with self.assertRaises(TinyRuntimeError):
            run_source(src, ["0"])

    def test_compile_error_via_api_raises_compile_error(self):
        with self.assertRaises(CompileError) as cm:
            run_source("x = 1;", filename="t.tiny")
        self.assertIn("t.tiny:1:1: semantic error: variable 'x' is not declared", str(cm.exception))

    def test_known_values(self):
        out = read(example("fibonacci", ".expected")).split()
        self.assertEqual(out, "0 1 1 2 3 5 8 13 21 34 55 89".split())
        self.assertEqual(read(example("gcd", ".expected")).split()[-1], "12")


class CliOptionTests(unittest.TestCase):
    def test_tokens_option(self):
        code, out, _ = cli(["examples/hello.tiny", "--tokens", "--check"])
        self.assertEqual(code, 0)
        self.assertIn("=== Tokens ===", out)
        self.assertIn("2:1      write    write", out)
        self.assertIn("STRING", out)

    def test_ast_option(self):
        code, out, _ = cli(["examples/hello.tiny", "--ast", "--check"])
        self.assertIn("=== AST ===", out)
        self.assertIn("Write", out)

    def test_symbols_option(self):
        code, out, _ = cli(["examples/scopes.tiny", "--symbols", "--check"])
        self.assertIn("=== Symbol table ===", out)
        self.assertIn("x#1", out)

    def test_ir_option(self):
        code, out, _ = cli(["examples/arithmetic.tiny", "--ir", "--check"])
        self.assertIn("=== Three-address code ===", out)
        self.assertIn("$t1 = ", out)

    def test_code_option(self):
        code, out, _ = cli(["examples/loop.tiny", "--code", "--check"])
        self.assertIn("=== Stack-machine code ===", out)
        self.assertIn("JZ", out)
        self.assertIn("HALT", out)

    def test_all_option_shows_every_stage_then_output(self):
        code, out, _ = cli(["examples/hello.tiny", "--all"])
        self.assertEqual(code, 0)
        positions = [out.index(h) for h in ("=== Tokens ===", "=== AST ===",
                                            "=== Symbol table ===",
                                            "=== Three-address code ===",
                                            "=== Stack-machine code ===",
                                            "=== Program output ===")]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(out.rstrip().endswith("Hello, Tiny!"))

    def test_check_does_not_run(self):
        code, out, err = cli(["examples/hello.tiny", "--check"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("compiled successfully", err)

    def test_input_option(self):
        code, out, _ = cli(["examples/gcd.tiny", "--input", "100 75"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split()[-1], "25")

    def test_ir_backend_gives_same_output(self):
        a = cli(["examples/fibonacci.tiny"])
        b = cli(["examples/fibonacci.tiny", "--backend", "ir"])
        self.assertEqual(a, b)

    def test_trace_goes_to_stderr(self):
        code, out, err = cli(["examples/hello.tiny", "--trace"])
        self.assertEqual(out, "Hello, Tiny!\n")
        self.assertIn("PRINT_STR", err)

    def test_max_steps(self):
        code, out, err = cli(["examples/loop.tiny", "--max-steps", "10"])
        self.assertEqual(code, 3)
        self.assertIn("execution stopped after 10 steps", err)

    def test_tokens_still_shown_for_lexical_errors(self):
        code, out, err = cli(["examples/invalid_character.tiny", "--tokens"])
        self.assertEqual(code, 1)
        self.assertIn("=== Tokens ===", out)
        self.assertIn("invalid character", err)

    def test_warnings_are_shown_but_do_not_fail(self):
        src = os.path.join(ROOT, "tests", "_tmp_warn.tiny")
        with open(src, "w") as fh:
            fh.write("var unused: int = 1;\nwrite 1;\n")
        try:
            code, out, err = cli(["tests/_tmp_warn.tiny"])
            self.assertEqual((code, out), (0, "1\n"))
            self.assertIn("warning: variable 'unused'", err)
            code, out, err = cli(["tests/_tmp_warn.tiny", "--no-warnings"])
            self.assertEqual(err, "")
        finally:
            os.remove(src)

    def test_missing_file(self):
        code, out, err = cli(["examples/does_not_exist.tiny"])
        self.assertEqual(code, 4)
        self.assertIn("cannot read", err)

    def test_missing_argument_is_usage_error(self):
        code, out, err = cli([])
        self.assertEqual(code, 2)
        self.assertIn("usage:", err)

    def test_module_entry_point(self):
        proc = subprocess.run([sys.executable, "-m", "tiny_compiler", "examples/hello.tiny"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.replace("\r\n", "\n"), "Hello, Tiny!\n")

    def test_version(self):
        code, out, err = cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("tiny-compiler", out)

    def test_stdin_input_when_no_input_option(self):
        code, out, _ = cli(["examples/gcd.tiny"], "12 18\n")
        self.assertEqual(out.split()[-1], "6")

    def test_utf8_bom_source_is_accepted(self):
        src = os.path.join(ROOT, "tests", "_tmp_bom.tiny")
        with open(src, "wb") as fh:
            fh.write(b"\xef\xbb\xbfwrite 5;\n")
        try:
            code, out, _ = cli(["tests/_tmp_bom.tiny"])
            self.assertEqual((code, out), (0, "5\n"))
        finally:
            os.remove(src)


class ErrorQualityTests(unittest.TestCase):
    """Source code that must be rejected with an understandable message."""

    def messages(self, src):
        with self.assertRaises(CompileError) as cm:
            run_source(src)
        return [d.message for d in cm.exception.diagnostics]

    def test_no_python_traceback_for_garbage_input(self):
        for src in ["@@@", "var", "if", "{{{{", "write", "x =", "var x: int = (", "\"", "/*"]:
            with self.subTest(src=src):
                self.assertTrue(self.messages(src))

    def test_error_messages_name_the_problem(self):
        self.assertIn("variable 'q' is not declared", self.messages("write q;")[0])
        self.assertIn("expected ';'", self.messages("var x: int = 1")[0])
        self.assertIn("invalid character '$'", self.messages("var x: int = 1 $ 2;")[0])


if __name__ == "__main__":
    unittest.main()
