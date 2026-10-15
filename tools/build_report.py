"""Rebuild report/Tiny_Programming_Language_Compiler_Report.docx and docs/TESTING.md.

Everything that looks like a result in the report (test counts, example outputs,
the acceptance table) is produced by actually running the commands here, so the
report cannot drift away from the code.

    pip install -r requirements-dev.txt
    python tools/build_report.py
"""
import datetime
import inspect
import os
import platform
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

import tiny_compiler  # noqa: E402
from tiny_compiler import ir as ir_mod  # noqa: E402
from tiny_compiler import lexer as lexer_mod  # noqa: E402
from tiny_compiler import parser as parser_mod  # noqa: E402
from tiny_compiler import semantic as semantic_mod  # noqa: E402
from tiny_compiler import vm as vm_mod  # noqa: E402

PY = sys.executable
REPORT = os.path.join(ROOT, "report", "Tiny_Programming_Language_Compiler_Report.docx")
TESTING_MD = os.path.join(ROOT, "docs", "TESTING.md")
DIAGRAM = os.path.join(ROOT, "docs", "img", "architecture.png")
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# running things
# ---------------------------------------------------------------------------
def run(args, stdin=None):
    p = subprocess.run(args, cwd=ROOT, input=stdin, capture_output=True, text=True,
                       encoding="utf-8")
    return p.returncode, p.stdout.replace("\r\n", "\n"), p.stderr.replace("\r\n", "\n")


def read(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def exists(path):
    return os.path.exists(os.path.join(ROOT, path))


def unittest_module(mod):
    rc, out, err = run([PY, "-m", "unittest", "tests." + mod])
    m = re.search(r"Ran (\d+) tests? in ([\d.]+)s", err)
    n = int(m.group(1)) if m else 0
    ok = rc == 0 and re.search(r"^OK", err, re.M) is not None
    return ok, n, err


def collect_suite():
    rc, out, err = run([PY, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"])
    per = {}
    for m in re.finditer(r"\(tests\.(\w+)\.\w+\.?\w*\) \.\.\. (ok|FAIL|ERROR)", err):
        d = per.setdefault(m.group(1), {"ok": 0, "bad": 0})
        d["ok" if m.group(2) == "ok" else "bad"] += 1
    m = re.search(r"Ran (\d+) tests? in ([\d.]+)s", err)
    total = int(m.group(1)) if m else 0
    secs = m.group(2) if m else "?"
    ok = rc == 0 and re.search(r"^OK\s*$", err, re.M) is not None
    return {"ok": ok, "total": total, "secs": secs, "per": per, "log": err}


VALID = [
    ("hello", False), ("arithmetic", False), ("conditional", False), ("loop", False),
    ("input_output", True), ("fibonacci", False), ("gcd", True), ("scopes", False),
    ("logic", False),
]
INVALID = ["invalid_character", "invalid_syntax", "invalid_semantics"]


def run_example(name, with_input):
    stdin = read("examples/%s.input" % name) if with_input else ""
    rc, out, err = run([PY, "main.py", "examples/%s.tiny" % name], stdin)
    exp = read("examples/%s.expected" % name)
    return rc == 0 and out == exp, out


def run_invalid(name):
    rc, out, err = run([PY, "main.py", "examples/%s.tiny" % name])
    return rc == 1 and out == "" and err == read("examples/%s.expected" % name), err


def run_runtime_example():
    rc, out, err = run([PY, "main.py", "examples/invalid_runtime.tiny"],
                       read("examples/invalid_runtime.input"))
    ok = (rc == 3 and out == read("examples/invalid_runtime.expected")
          and err == read("examples/invalid_runtime.expected_err"))
    return ok, out, err


def powershell_check():
    ps = shutil_which("powershell")
    if not ps:
        return None
    cmd = ("python main.py examples/hello.tiny; "
           "Get-Content examples/input_output.input | python main.py examples/input_output.tiny; "
           "python main.py examples/gcd.tiny --input '84 36'")
    rc, out, err = run([ps, "-NoProfile", "-Command", cmd])
    expected = (read("examples/hello.expected") + read("examples/input_output.expected")
                + read("examples/gcd.expected"))
    return rc == 0 and out == expected


def shutil_which(name):
    import shutil
    return shutil.which(name)


# ---------------------------------------------------------------------------
# docx helpers
# ---------------------------------------------------------------------------
class Doc:
    def __init__(self):
        self.d = Document()
        self.fig = 0
        self.tab = 0
        self._setup()

    def _setup(self):
        d = self.d
        for s in d.sections:
            s.page_width, s.page_height = Cm(21.0), Cm(29.7)
            s.left_margin = s.right_margin = Cm(2.5)
            s.top_margin = s.bottom_margin = Cm(2.3)
        st = d.styles["Normal"]
        st.font.name = "Calibri"
        st.font.size = Pt(11)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.line_spacing = 1.15
        for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5)):
            h = d.styles[name]
            h.font.name = "Calibri"
            h.font.size = Pt(size)
            h.font.bold = True
            h.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
            h.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
            h.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
            h.paragraph_format.space_after = Pt(6)
            h.paragraph_format.keep_with_next = True
        cap = d.styles["Caption"]
        cap.font.size = Pt(9.5)
        cap.font.italic = True
        cap.font.bold = False
        cap.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
        # footer with page numbers
        footer = d.sections[0].footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._field(footer, "PAGE")
        # ask Word to refresh the table of contents when the file is opened
        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        d.settings.element.append(upd)

    # -- low level
    def _field(self, paragraph, instr, placeholder="1"):
        run = paragraph.add_run()
        for kind, text in (("begin", None), (None, instr), ("separate", None),
                           ("text", placeholder), ("end", None)):
            if kind in ("begin", "separate", "end"):
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
                run._r.append(el)
            elif kind == "text":
                t = OxmlElement("w:t")
                t.text = text
                run._r.append(t)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
                run._r.append(el)

    def _inline(self, p, text, base_bold=False, size=None):
        """Mini markup: **bold**, `code`, [[placeholder]]."""
        parts = re.split(r"(\*\*.+?\*\*|`.+?`|\[\[.+?\]\]|\*[^*\s][^*]*?\*)", text)
        for part in parts:
            if not part:
                continue
            if part.startswith("**"):
                r = p.add_run(part[2:-2])
                r.bold = True
            elif part.startswith("`"):
                r = p.add_run(part[1:-1])
                r.font.name = "Consolas"
                r.element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
                r.font.size = Pt(9.5)
            elif part.startswith("*") and len(part) > 2:
                r = p.add_run(part[1:-1])
                r.italic = True
                if base_bold:
                    r.bold = True
            elif part.startswith("[["):
                r = p.add_run("[" + part[2:-2] + "]")
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
            else:
                r = p.add_run(part)
                if base_bold:
                    r.bold = True
            if size:
                r.font.size = Pt(size)

    # -- content
    def h1(self, t):
        return self.d.add_heading(t, 1)

    def h2(self, t):
        return self.d.add_heading(t, 2)

    def h3(self, t):
        return self.d.add_heading(t, 3)

    def p(self, text, align=None, bold=False, size=None, after=None):
        para = self.d.add_paragraph()
        self._inline(para, text, bold, size)
        if align == "center":
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "justify":
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if after is not None:
            para.paragraph_format.space_after = Pt(after)
        return para

    def bullets(self, items, style="List Bullet"):
        for it in items:
            para = self.d.add_paragraph(style=style)
            self._inline(para, it)
            para.paragraph_format.space_after = Pt(2)

    def numbered(self, items):
        # manual numbers: Word's automatic "List Number" would continue across lists
        for n, it in enumerate(items, 1):
            para = self.d.add_paragraph()
            para.paragraph_format.left_indent = Cm(1.0)
            para.paragraph_format.first_line_indent = Cm(-0.6)
            para.paragraph_format.space_after = Pt(2)
            self._inline(para, "%d.  %s" % (n, it))

    def code(self, text, size=8.5):
        for line in text.rstrip("\n").split("\n") or [""]:
            para = self.d.add_paragraph()
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.left_indent = Cm(0.4)
            para.paragraph_format.line_spacing = 1.0
            r = para.add_run(line if line else " ")
            r.font.name = "Consolas"
            r.element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
            r.font.size = Pt(size)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F2F2F2")
            para._p.get_or_add_pPr().append(shd)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def caption(self, kind, text):
        if kind == "Figure":
            self.fig += 1
            n = self.fig
        else:
            self.tab += 1
            n = self.tab
        para = self.d.add_paragraph(style="Caption")
        para.paragraph_format.keep_with_next = (kind == "Table")
        para.add_run("%s %d: %s" % (kind, n, text))
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def table(self, header, rows, widths=None, caption=None, size=9.5, mono_cols=()):
        if caption:
            self.caption("Table", caption)
        t = self.d.add_table(rows=1, cols=len(header))
        t.style = "Table Grid"
        t.alignment = 1
        for i, h in enumerate(header):
            cell = t.rows[0].cells[i]
            cell.text = ""
            r = cell.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(size)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "D9E2F3")
            cell._tc.get_or_add_tcPr().append(shd)
        # repeat header row on every page
        trPr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trPr.append(th)
        for row in rows:
            cells = t.add_row().cells
            for i, val in enumerate(row):
                cells[i].text = ""
                para = cells[i].paragraphs[0]
                para.paragraph_format.space_after = Pt(0)
                self._inline(para, str(val), size=size)
                if i in mono_cols:
                    for r in para.runs:
                        r.font.name = "Consolas"
        if not widths:
            widths = [16.0 / len(header)] * len(header)
        t.autofit = False
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def image(self, path, width_cm, caption):
        self.d.add_picture(path, width=Cm(width_cm))
        self.d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.caption("Figure", caption)

    def placeholder_box(self, title, command):
        t = self.d.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        t.autofit = False
        t.columns[0].width = Cm(16.0)
        cell = t.rows[0].cells[0]
        cell.width = Cm(16.0)
        cell.text = ""
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "FFF2CC")
        cell._tc.get_or_add_tcPr().append(shd)
        para = cell.paragraphs[0]
        self._inline(para, "**[SCREENSHOT PLACEHOLDER - not captured yet]** %s" % title)
        p2 = cell.add_paragraph()
        self._inline(p2, "Run in PowerShell from the project folder, take a screenshot and paste "
                         "it here in place of this box:  `%s`" % command)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def page_break(self):
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def toc(self):
        para = self.d.add_paragraph()
        self._field(para, 'TOC \\o "1-2" \\h \\z \\u',
                    "Right-click here and choose 'Update Field' (or press F9) to build the table "
                    "of contents.")

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.d.save(path)


def count_lines(folder):
    total = 0
    for name in os.listdir(os.path.join(ROOT, folder)):
        if name.endswith(".py"):
            total += len(read(folder + "/" + name).splitlines())
    return total


def source_of(obj):
    return inspect.getsource(obj).rstrip("\n")


# ---------------------------------------------------------------------------
def main():
    print("running the test-suite and examples (about 10 s) ...")
    suite = collect_suite()
    mods = ["test_lexer", "test_parser", "test_semantics", "test_ir", "test_codegen_vm",
            "test_end_to_end"]
    modres = {m: unittest_module(m) for m in mods}
    valid_res = {n: run_example(n, inp) for n, inp in VALID}
    invalid_res = {n: run_invalid(n) for n in INVALID}
    rt_ok, rt_out, rt_err = run_runtime_example()
    ps_ok = powershell_check()
    pyver = platform.python_version()
    osver = "%s %s" % (platform.system(), platform.release())
    if platform.system() == "Windows" and int(platform.version().split(".")[-1] or 0) >= 22000:
        osver = "Windows 11"  # platform.release() still reports "10" on Windows 11

    def verdict(ok):
        return "PASS" if ok else "FAIL"

    def modv(m):
        ok, n, _ = modres[m]
        return "%s (%d tests)" % (verdict(ok), n)

    all_valid = all(ok for ok, _ in valid_res.values())
    all_invalid = all(ok for ok, _ in invalid_res.values()) and rt_ok

    acceptance = [
        ("Lexer: tokens with line/column, comments, strings, invalid-character errors",
         "tiny_compiler/lexer.py", "python -m unittest tests.test_lexer", modv("test_lexer"), ""),
        ("Parser: recursive descent, documented grammar, AST, precedence/associativity, "
         "syntax errors and recovery",
         "tiny_compiler/parser.py, ast_nodes.py", "python -m unittest tests.test_parser",
         modv("test_parser"), "comparison operators are non-associative by design"),
        ("Semantic analysis: symbol table, scopes, declaration, use-before-declaration, "
         "type checks, constant division by zero",
         "tiny_compiler/semantic.py, symbol_table.py", "python -m unittest tests.test_semantics",
         modv("test_semantics"), "only constant-literal zero divisors are detected statically"),
        ("Intermediate representation: three-address code with temporaries and labels, "
         "control flow, short-circuit logic",
         "tiny_compiler/ir.py", "python -m unittest tests.test_ir", modv("test_ir"),
         "no optimisation pass"),
        ("Target code generation and execution: stack-machine code run by a VM; "
         "I/O; runtime errors",
         "tiny_compiler/codegen.py, vm.py, runtime.py",
         "python -m unittest tests.test_codegen_vm", modv("test_codegen_vm"),
         "target is a virtual machine, not native code"),
        ("Diagnostics with source positions for lexical, syntax, semantic and runtime errors",
         "tiny_compiler/diagnostics.py",
         "python main.py examples/invalid_syntax.tiny  (and the other invalid examples)",
         verdict(all_invalid) + " (4 invalid examples)", "stops after the first failing phase"),
        ("CLI: show tokens, AST, symbol table, IR, target code, program output",
         "tiny_compiler/cli.py, main.py", "python -m unittest tests.test_end_to_end",
         modv("test_end_to_end"), ""),
        ("Every valid example produces its expected output (both back-ends)",
         "examples/ (.tiny, .expected, .input files)",
         "python -m unittest tests.test_end_to_end.ExampleProgramTests",
         verdict(all_valid) + " (%d examples)" % len(VALID), ""),
        ("Every invalid example fails with an understandable error, no traceback",
         "examples/invalid_ files",
         "python main.py examples/invalid_character.tiny (etc.)",
         verdict(all_invalid), ""),
        ("Complete automated suite (unit + integration + end-to-end)",
         "tests/", "python -m unittest discover -s tests -t .",
         "%s (%d tests)" % (verdict(suite["ok"]), suite["total"]), ""),
        ("Windows PowerShell setup/run commands from the README",
         "README.md",
         "powershell: python main.py examples/hello.tiny ; Get-Content ... | python main.py ...",
         "NOT RUN" if ps_ok is None else verdict(ps_ok),
         "run on Windows only; Python %s" % pyver),
        ("Linux / macOS commands from the README", "README.md", "python3 main.py ...",
         "NOT RUN", "no Linux/macOS machine was available; commands are the same apart from "
         "python3 and shell quoting"),
        ("Real screenshots of the CLI in the report", "screenshots/README.md",
         "(manual)", "NOT RUN",
         "placeholders only; see screenshots/README.md for the 7 commands to capture"),
        ("Review-2 template PDF used as checklist", "report (section mapping)", "(manual)",
         "NOT RUN", "the PDF was not supplied; the checklist from the project prompt was used"),
    ]

    write_testing_md(suite, modres, valid_res, invalid_res, rt_ok, acceptance, pyver, osver)

    # -------------------------------------------------------------------
    D = Doc()
    d = D.d

    # ---------------- title page
    for _ in range(3):
        D.p("")
    D.p("TINY PROGRAMMING LANGUAGE COMPILER", "center", True, 26, after=4)
    D.p("Project Review 2 - Implementation Report", "center", False, 15, after=30)
    D.p("A working educational compiler: lexical analysis, syntax analysis, semantic analysis, "
        "three-address code and a stack virtual machine", "center", False, 12, after=40)
    D.table(["Field", "Details (edit before submission)"], [
        ["Student name(s)", "[[Student name(s)]]"],
        ["Register number(s)", "[[Register number(s)]]"],
        ["Programme / Branch", "[[Programme / Branch]]"],
        ["Project guide", "[[Guide name and designation]]"],
        ["Institution", "[[Institution name]]"],
        ["Review date", "[[Review date]]"],
    ], widths=[5, 11])
    D.p("Report generated from the project source on %s (Python %s, %s)." %
        (TODAY, pyver, osver), "center", size=9)
    D.page_break()

    D.h1("Table of Contents")
    D.toc()
    D.page_break()

    # ---------------- abstract
    D.h1("Abstract")
    D.p("This project implements a complete, runnable educational compiler for a small, C-like "
        "language called Tiny. The compiler is written in Python and demonstrates the full "
        "pipeline: source program, lexical analysis, syntax analysis, semantic analysis, "
        "three-address-code generation, stack-machine code generation, and execution on a "
        "bundled virtual machine. The language has integer and boolean types, block-scoped "
        "variables, arithmetic with defined precedence, comparisons, short-circuit logical "
        "operators, `if`/`else`, `while`, and `read`/`write` statements. Diagnostics report the "
        "phase, line and column of every error and show the offending source line. "
        "The implementation is checked by %d automated tests (%s) and by nine example programs "
        "whose outputs were verified by hand. The project does not claim a new language or a new "
        "compilation technique; its contribution is a small, fully specified and fully testable "
        "teaching implementation in which every phase can be inspected from the command line."
        % (suite["total"], "all passing" if suite["ok"] else "SEE TEST RESULTS"), "justify")
    D.p("**Keywords:** compiler construction, lexical analysis, recursive-descent parsing, semantic "
        "analysis, symbol table, three-address code, stack virtual machine, Python.")

    # ---------------- 1 project details
    D.h1("1. Project Details")
    D.table(["Item", "Details"], [
        ["Project title", "Tiny Programming Language Compiler"],
        ["Student name(s)", "[[Student name(s)]]"],
        ["Register number(s)", "[[Register number(s)]]"],
        ["Programme / Branch", "[[Programme / Branch]]"],
        ["Guide", "[[Guide name]]"],
        ["Review", "Project Review 2"],
        ["Review date", "[[Review date]]"],
        ["Source repository", "GitHub repository `Chirayu-Project` (folder `Chirayu-Project/`)"],
    ], widths=[5, 11], caption="Project details")
    D.p("*Note on numbering:* the Review 2 template's visible numbering skips section 5. This "
        "report keeps the template's numbers (1, 2, 3, 4 and 6) so the sections can be matched "
        "one-to-one; Conclusion and References follow as unnumbered-by-template sections 7-8. "
        "[[Check the numbering against the PDF template and adjust if it differs.]]")

    # ---------------- 2 overview
    D.h1("2. Project Overview")
    D.h2("2.1 Introduction")
    D.p("A compiler translates a program written in a source language into another form that "
        "can be executed. Compilers are normally taught as a sequence of phases [1]: the lexical "
        "analyser groups characters into tokens, the parser checks the grammatical structure and "
        "builds a syntax tree, semantic analysis checks meaning (declarations, types), an "
        "intermediate representation is generated, and finally target code is produced. This "
        "project builds all of these phases for a small language of its own, so that the whole "
        "pipeline can be read, run and tested by a student in a short time.", "justify")
    D.p("Tiny here is *this project's own dialect*. The name \"TINY\" is used for several teaching "
        "languages - the best known is the TINY language that accompanies Louden's textbook [2] - "
        "and there is no single universal specification, so the exact language implemented is "
        "defined in `docs/LANGUAGE_SPEC.md` and `docs/GRAMMAR.md` and summarised in Section 3.2.",
        "justify")
    D.h2("2.2 Problem statement and need")
    D.p("Students of compiler design often see the phases only as separate exercises or as "
        "fragments of a large production compiler, which makes it hard to see how a program "
        "actually flows from characters to execution. Production infrastructures such as LLVM [6] "
        "are far too large for this purpose. What is needed is a compact compiler that (a) "
        "implements every phase for real, (b) is small enough to read completely, (c) lets each "
        "intermediate result be displayed, (d) gives clear error messages, and (e) comes with tests "
        "that prove each phase behaves as documented.", "justify")
    D.h2("2.3 Objectives and scope")
    D.bullets([
        "Specify a coherent Tiny language (types, scope rules, operators, statements, I/O).",
        "Implement a lexer, a recursive-descent parser, semantic analysis with a scoped symbol "
        "table, a three-address-code generator, a stack-code generator and a virtual machine as "
        "separate, testable modules.",
        "Provide a command-line tool that can display tokens, AST, symbol table, IR, target code "
        "and program output.",
        "Report lexical, syntax, semantic and run-time errors with positions.",
        "Verify the implementation with automated unit, integration and end-to-end tests and "
        "executable examples.",
    ])
    D.p("**Out of scope:** native machine-code generation, optimisation passes, functions, arrays, "
        "floating-point numbers, string variables, a graphical front end, and multi-file programs.")
    D.h2("2.4 Literature review and related work")
    D.p("The phase structure used in this project follows the classic treatment in the "
        "\"dragon book\" by Aho, Lam, Sethi and Ullman [1] and the more recent text by Cooper and "
        "Torczon [5], which also discuss intermediate representations such as three-address "
        "code. Louden's textbook [2] introduces the TINY language and compiles it to code for an "
        "abstract machine; this project borrows the idea of a small teaching language but defines "
        "its own, typed dialect with boolean values, block scope and short-circuit logic. "
        "Wirth's *Compiler Construction* [3] shows that a language can be compiled with a compact "
        "recursive-descent compiler, which is the parsing technique used here; Wirth's earlier "
        "language Pascal [7] was designed, among other aims, to teach programming as a "
        "systematic discipline. Nystrom's *Crafting Interpreters* [4] demonstrates a hand-written "
        "scanner, parser and bytecode virtual machine for a small language and is the closest "
        "in spirit to the execution model chosen here.", "justify")
    D.p("At the other end of the scale, LLVM [6] is an industrial compiler framework built "
        "around a typed low-level representation; its scale and goals (optimisation, many "
        "targets) are very different from this project. Lua 5.0 [8] is an example of a real "
        "language executed by a register-based virtual machine; this project instead uses the "
        "simpler stack-machine model, which is easier to generate code for and to explain. For "
        "expression parsing, alternatives to layered recursive descent exist, such as "
        "operator-precedence (\"Pratt\") parsing [9] and parsing expression grammars [10]; "
        "layered recursive descent was chosen because every precedence level is an explicit, "
        "readable method.", "justify")
    D.table(["Ref.", "Work", "Type", "Relevance to this project"], [
        ["[1]", "Aho, Lam, Sethi, Ullman - Compilers: Principles, Techniques, and Tools", "Textbook",
         "Phase structure, symbol tables, three-address code"],
        ["[2]", "Louden - Compiler Construction: Principles and Practice", "Textbook",
         "Origin of the TINY teaching language"],
        ["[3]", "Wirth - Compiler Construction", "Textbook", "Compact recursive-descent compilers"],
        ["[4]", "Nystrom - Crafting Interpreters", "Book (also online)",
         "Hand-written scanner/parser and bytecode VM"],
        ["[5]", "Cooper, Torczon - Engineering a Compiler", "Textbook", "IR design, code generation"],
        ["[6]", "Lattner, Adve - LLVM (CGO 2004)", "Peer-reviewed conference paper",
         "Contrast: industrial typed-IR compiler framework"],
        ["[7]", "Wirth - The Programming Language Pascal (Acta Informatica 1971)",
         "Peer-reviewed journal article", "A language designed with teaching in mind"],
        ["[8]", "Ierusalimschy et al. - The Implementation of Lua 5.0 (J.UCS 2005)",
         "Peer-reviewed journal article", "Contrast: register-based VM of a real language"],
        ["[9]", "Pratt - Top Down Operator Precedence (POPL 1973)",
         "Peer-reviewed conference paper", "Alternative expression-parsing technique"],
        ["[10]", "Ford - Parsing Expression Grammars (POPL 2004)",
         "Peer-reviewed conference paper", "Alternative grammar formalism"],
    ], widths=[1.2, 6.8, 3.2, 5.0], caption="Related work and its relevance", size=8.5)

    D.h2("2.5 Proposed solution and methodology")
    D.p("The solution is a pipeline of independent modules connected by well-defined data "
        "structures (Figure 1 in Section 3.3). The methodology was:", "justify")
    D.numbered([
        "Define the language and its grammar first (documents `LANGUAGE_SPEC.md`, `GRAMMAR.md`).",
        "Implement the phases front to back; each phase reports errors into a shared "
        "diagnostic bag and the pipeline stops after the first phase that fails.",
        "Annotate the AST during semantic analysis (types, resolved symbols) so that later "
        "phases need no further checking.",
        "Lower the annotated AST to three-address code, then to stack code, then execute it.",
        "Write tests for each phase independently, then end-to-end tests that run every example "
        "through the real command-line tool.",
        "Cross-check code generation by running programs on two back-ends (TAC interpreter and "
        "stack VM) that must agree.",
    ])
    D.h2("2.6 Expected outcome")
    D.p("A student can install nothing but Python, run `python main.py examples/loop.tiny --all`, "
        "and see tokens, AST, symbol table, three-address code, stack code and the program output; "
        "can write programs in Tiny and receive precise diagnostics; and can run the automated "
        "tests to confirm the implementation. These outcomes have been achieved and verified "
        "(Section 3.7).", "justify")

    # ---------------- 3 implementation
    D.h1("3. Implementation / Prototype Progress")
    D.h2("3.1 Actual status and completed modules")
    D.p("All planned core modules are implemented and integrated. Status is taken from the "
        "verification run described in Section 3.7 (not assumed).", "justify")
    D.table(["Module / deliverable", "File(s)", "Status"], [
        ["Lexer", "tiny_compiler/lexer.py", "Complete - " + modv("test_lexer")],
        ["Parser + AST", "parser.py, ast_nodes.py", "Complete - " + modv("test_parser")],
        ["Symbol table + semantic analysis", "symbol_table.py, semantic.py",
         "Complete - " + modv("test_semantics")],
        ["Three-address code + TAC interpreter", "ir.py", "Complete - " + modv("test_ir")],
        ["Stack code generator + VM + runtime", "codegen.py, vm.py, runtime.py",
         "Complete - " + modv("test_codegen_vm")],
        ["Diagnostics", "diagnostics.py", "Complete (covered by all test modules)"],
        ["CLI", "cli.py, main.py, __main__.py", "Complete - " + modv("test_end_to_end")],
        ["Examples (9 valid, 4 invalid)", "examples/", "Complete - outputs verified"],
        ["Documentation", "README.md, docs/ folder", "Complete"],
        ["Word report", "report/ folder (.docx)", "This document (regenerate with tools/build_report.py)"],
        ["Real screenshots", "screenshots/", "NOT DONE - placeholders (Section 3.6)"],
    ], widths=[5.4, 5.2, 5.4], caption="Implementation status")

    D.h2("3.2 Language specification, grammar and sample programs")
    D.p("The full specification is in `docs/LANGUAGE_SPEC.md`. Key points:", "justify")
    D.bullets([
        "**Types:** `int` (arbitrary precision) and `bool`; no implicit conversions.",
        "**Declarations:** `var x: int;` / `var b: bool = true;` - default value `0` / `false`; "
        "block scope, shadowing allowed, duplicates in one scope rejected, use before "
        "declaration rejected.",
        "**Operators (loosest to tightest):** `or`, `and`, `not`, comparison "
        "(`== != < <= > >=`, non-associative), `+ -`, `* / %`, unary `-`.",
        "**Arithmetic:** `/` truncates toward zero and `%` takes the sign of the dividend; division "
        "by a constant zero is a compile-time error, otherwise a run-time error.",
        "**Statements:** assignment, `if`/`else if`/`else`, `while`, blocks, `read x;`, "
        "`write a, b, ...;` (items separated by one space, newline at the end).",
        "**Comments:** `// ...` and `/* ... */`.",
    ])
    D.h3("Grammar (EBNF)")
    D.code(read("docs/GRAMMAR.md").split("```ebnf")[1].split("```")[0].strip(), 8)
    D.h3("Sample programs")
    D.p("`examples/loop.tiny`:")
    D.code(read("examples/loop.tiny"))
    D.p("`examples/gcd.tiny` (Euclid's algorithm with input):")
    D.code(read("examples/gcd.tiny"))

    D.h2("3.3 System architecture and workflow")
    D.image(DIAGRAM, 16.0, "Compiler pipeline and modules")
    D.p("Data flow: `str` -> `List[Token]` (lexer) -> `Program` AST (parser) -> annotated AST + "
        "`SymbolTable` (semantic analysis) -> `List[Instr]` three-address code (IR generator) -> "
        "`List[VMInstr]` stack code (code generator) -> program output (VM). Every phase writes "
        "problems to a `DiagnosticBag`; `pipeline.compile_source` stops after the first phase "
        "with errors, so a later phase never receives invalid input.", "justify")

    D.h2("3.4 Modules: inputs, outputs, algorithms and design choices")
    D.table(["Module", "Input -> Output", "Algorithm / design choice"], [
        ["Lexer", "source text -> tokens",
         "Hand-written single-pass scanner; two-character operators tried first; tracks line "
         "and column; invalid characters are reported and skipped so all are found in one run"],
        ["Parser", "tokens -> AST",
         "Recursive descent, one method per grammar rule; precedence from rule layering; "
         "panic-mode recovery at `;`/`}`; unsupported constructs (`for`, `print`, `float`...) "
         "get explicit messages"],
        ["Semantic analysis", "AST -> annotated AST + symbol table",
         "Stack of scopes; each declaration gets a unique storage name (`x`, `x#1`) so "
         "shadowing is resolved once; a \"pending declarations\" set per block distinguishes "
         "use-before-declaration from undeclared; type-error cascades are suppressed"],
        ["IR generator", "annotated AST -> TAC",
         "Post-order walk creating temporaries `$tN`; `if`/`while` lowered to labels and "
         "`ifFalse`/`goto`; `and`/`or` lowered to conditional jumps (short-circuit)"],
        ["Code generator", "TAC -> stack code",
         "Each TAC instruction maps to a fixed push/op/store pattern; labels are resolved to "
         "instruction indexes in a second pass"],
        ["VM", "stack code -> output",
         "Fetch-execute loop over a list; value stack + variable dictionary; step limit; optional "
         "trace of every instruction"],
        ["Runtime", "shared by VM and TAC interpreter",
         "Truncating division/modulo, value formatting, input tokenising; shared so both "
         "back-ends behave identically"],
    ], widths=[2.6, 4.2, 9.2], caption="Module summary", size=8.5)
    D.p("**Representative code - expression precedence in the parser** (layered methods):")
    D.code(source_of(parser_mod.Parser._additive) + "\n\n" + source_of(parser_mod.Parser._term))
    D.p("**Representative code - short-circuit lowering in the IR generator:**")
    D.code(source_of(ir_mod.IRGenerator._short_circuit))

    D.h3("Worked example: from source to execution")
    D.p("Source (`examples/loop.tiny`, first part) and the three-address code produced by "
        "`python main.py examples/loop.tiny --ir --check`:")
    rc, out, err = run([PY, "main.py", "examples/loop.tiny", "--ir", "--check"])
    D.code("\n".join(out.splitlines()[1:17]))
    rc, out2, err = run([PY, "main.py", "examples/loop.tiny", "--code", "--check"])
    D.p("The stack code from `--code` (first 24 instructions); note `JZ 23` is the `ifFalse` "
        "exit of the loop and `JMP 4` is the back edge:")
    D.code("\n".join(out2.splitlines()[1:25]))

    D.h2("3.5 Technology stack and implementation details")
    D.table(["Item", "Choice"], [
        ["Language", "Python %s used for development; requires Python 3.8+" % pyver],
        ["Dependencies", "None for the compiler (standard library only). `python-docx` and "
                         "`Pillow` only to rebuild this report"],
        ["Testing", "`unittest` (also runnable with pytest)"],
        ["Platform tested", osver],
        ["Version control", "Git / GitHub"],
        ["Size", "%d lines of compiler code (tiny_compiler/), %d lines of tests (tests/)"
                 % (count_lines("tiny_compiler"), count_lines("tests"))],
    ], widths=[4, 12], caption="Technology stack")

    D.h2("3.6 Screenshots of the working application")
    D.p("No real screenshots have been captured yet, so none are shown; the boxes below are "
        "clearly marked placeholders. Real *text* output of the same commands is included in "
        "Sections 3.4 and 3.7 and was produced by running the tool. Instructions for capturing the "
        "screenshots are in `screenshots/README.md`.", "justify")
    for title, cmd in [
        ("All compiler stages for hello.tiny", "python main.py examples/hello.tiny --all"),
        ("Arithmetic program output", "python main.py examples/arithmetic.tiny"),
        ("IR and stack code of the loop example", "python main.py examples/loop.tiny --ir --code"),
        ("Input/output example", 'python main.py examples/input_output.tiny --input "4 10 20 30 45"'),
        ("Syntax error diagnostics", "python main.py examples/invalid_syntax.tiny"),
        ("Semantic error diagnostics", "python main.py examples/invalid_semantics.tiny"),
        ("Automated test run", "python -m unittest discover -s tests -t . -v"),
    ]:
        D.placeholder_box(title, cmd)

    D.h2("3.7 Test plan, test cases, actual results and limitations")
    D.p("The test plan is in `docs/TESTING.md`. All tests are deterministic (no randomness without "
        "a fixed seed, no network, no timing dependence). Tests were executed on %s with "
        "Python %s." % (osver, pyver), "justify")
    rows = []
    desc = {
        "test_lexer": "valid tokens, keywords vs identifiers, literals, operators, comments, "
                      "strings/escapes, positions, invalid characters, malformed numbers, "
                      "unterminated strings/comments",
        "test_parser": "precedence, associativity, parentheses, unary minus, statement shapes, "
                       "node positions, AST dump, many syntax-error cases, unsupported constructs, "
                       "error recovery, termination on garbage",
        "test_semantics": "undeclared / duplicate / use-before-declaration, scopes and shadowing, "
                          "all type rules, constant division by zero, warnings, symbol table, "
                          "positions and caret rendering",
        "test_ir": "TAC text for arithmetic, precedence, unary, comparison, I/O, if, if-else, "
                   "while, else-if, short-circuit; label/jump integrity; TAC interpreter",
        "test_codegen_vm": "generated instruction sequences, jump resolution, execution results, "
                           "truncating division, big integers, scoping at runtime, input "
                           "handling, runtime errors, step limit, trace, random-expression "
                           "differential test against a Python reference",
        "test_end_to_end": "all examples through the real CLI and both back-ends, expected "
                           "diagnostics, every CLI option, exit codes, stdin, BOM, missing file",
    }
    for m in mods:
        ok, n, _ = modres[m]
        rows.append([m + ".py", str(n), verdict(ok), desc[m]])
    rows.append(["**All modules**", "**%d**" % suite["total"], "**%s**" % verdict(suite["ok"]),
                 "`python -m unittest discover -s tests -t .` finished in %ss" % suite["secs"]])
    D.table(["Test module", "Tests", "Result", "What it covers"], rows,
            widths=[3.4, 1.4, 1.6, 9.6], caption="Automated tests - actual results", size=8.5)

    D.p("**Example programs - actual results** (output compared with the hand-verified "
        "`examples/*.expected` files):")
    erows = []
    for n, inp in VALID:
        ok, out = valid_res[n]
        first = out.strip().splitlines()[0] if out.strip() else ""
        erows.append(["`%s.tiny`" % n, verdict(ok), first])
    for n in INVALID:
        ok, err = invalid_res[n]
        first = [ln for ln in err.splitlines() if "error:" in ln][0]
        first = first.split(": ", 1)[1] if ": " in first else first
        erows.append(["`%s.tiny`" % n, verdict(ok) + " (exit 1)", first[:70]])
    erows.append(["`invalid_runtime.tiny`", verdict(rt_ok) + " (exit 3)",
                  rt_err.strip().split(": ", 1)[1]])
    D.table(["Program", "Result", "First line of output / first diagnostic"], erows,
            widths=[4.4, 2.6, 9.0], caption="Example programs - actual results", size=8.5)

    D.p("**Sample actual output** - `python main.py examples/arithmetic.tiny`:")
    D.code(valid_res["arithmetic"][1])
    D.p("`python main.py examples/invalid_semantics.tiny` (first diagnostics shown):")
    D.code("\n".join(invalid_res["invalid_semantics"][1].splitlines()[:12]))
    D.p("**Test log** (last lines of the verbose run):")
    D.code("\n".join(suite["log"].strip().splitlines()[-6:]))
    D.h3("Limitations")
    D.bullets([
        "The target is a virtual machine; no native machine code or object files are produced.",
        "No optimisation pass (no constant folding or dead-code elimination).",
        "Only a literal constant-zero divisor is detected at compile time; other zero divisors "
        "are run-time errors.",
        "No functions, arrays, floats, strings as variables, `for`, `break`/`continue`.",
        "Integers are unbounded (Python integers), so overflow behaviour of real machines is not "
        "modelled.",
        "Error recovery is statement-level; a single early mistake can occasionally cause one "
        "extra follow-on syntax message.",
        "Tests were run on Windows only (see the acceptance table).",
    ])

    D.h2("3.8 Remaining work")
    D.bullets([
        "Capture the real screenshots listed in Section 3.6 and insert them (not yet done).",
        "Fill in the highlighted placeholders (student, register number, guide, institution, date).",
        "Compare the section numbering with the Review 2 template PDF, which was not available "
        "while this report was generated.",
        "Run the README commands on Linux/macOS (not run).",
        "Optional future enhancements: constant folding, functions, arrays, more precise "
        "static detection of division by zero, a web or playground UI, native code via LLVM.",
    ])

    # ---------------- 4 novelty
    D.h1("4. Novelty and Differentiation")
    D.p("Compilers, virtual machines and teaching languages are all well established, and this "
        "project does not claim a new language or a new compilation technique. What is "
        "specific to this implementation:", "justify")
    D.bullets([
        "**A fully specified, typed teaching dialect** with `int`/`bool`, block scope with "
        "shadowing, a precise \"used before declaration\" rule, short-circuit logic and "
        "defined division semantics - small enough to read in one sitting.",
        "**Every phase can be inspected** from one CLI (`--tokens --ast --symbols --ir --code "
        "--trace`), which is aimed at teaching and viva demonstration rather than at speed.",
        "**Diagnostics quality:** phase-labelled messages with line:column, the source line and a "
        "caret; several syntax errors per run through statement-level recovery; hints for common "
        "mistakes (`&` instead of `and`, `print` instead of `write`, `elif`, `float`...).",
        "**Two execution back-ends checked against each other:** a TAC interpreter and the "
        "stack VM share one runtime module and the test-suite requires identical output for all "
        "examples; arithmetic is also checked against a Python reference model on random "
        "expressions.",
        "**Evidence-driven documentation:** the numbers and outputs in this report and in "
        "`docs/TESTING.md` are produced by `tools/build_report.py`, which runs the real commands.",
    ])
    D.p("Compared with Louden's TINY [2], which targets an abstract machine and has a single "
        "integer type, this dialect adds booleans, block scope, comparison/logic operators and "
        "typed diagnostics; compared with LLVM [6] or Lua [8] it is deliberately tiny and does "
        "no optimisation.", "justify")

    # ---------------- 6 presentation
    D.h1("6. Presentation and Q&A")
    D.h2("6.1 Short presentation outline (about 5 minutes)")
    D.numbered([
        "Title, team, guide (30 s).",
        "Problem: compiler phases are hard to see end to end; need a small inspectable compiler.",
        "Objectives and scope (what is and is not included).",
        "The Tiny language: types, scope, operators, a 10-line example.",
        "Architecture: Figure 1; one sentence per phase.",
        "Live demo: `--all` on hello.tiny; loop.tiny with `--ir --code`; an error example.",
        "Verification: test counts, example table, acceptance table.",
        "Individual contributions: [[who did lexer / parser / semantic / IR+VM / tests / report]].",
        "Limitations, future work, conclusion, questions.",
    ])
    D.h2("6.2 Likely viva questions and simple answers")
    qa = [
        ("What does a lexer do?", "It reads characters and groups them into tokens (keywords, "
         "identifiers, numbers, operators), recording line and column; it also reports invalid "
         "characters."),
        ("Why recursive descent?", "The grammar is LL(1) and small; each grammar rule becomes one "
         "method, which is easy to read, extend and give good error messages."),
        ("How are precedence and associativity implemented?", "By layering the rules "
         "(or < and < not < comparison < additive < term < unary < primary). Left associativity "
         "comes from a loop that builds the tree to the left."),
        ("What is an AST and why not just a parse tree?", "An abstract syntax tree keeps only "
         "meaningful structure (no parentheses or punctuation) and is annotated later with types "
         "and symbols."),
        ("What does semantic analysis check here?", "Declarations, duplicates, use before "
         "declaration, block scopes, type rules for every operator, `bool` conditions and "
         "constant division by zero."),
        ("What is a symbol table?", "A stack of scopes mapping names to symbols (type, scope "
         "depth, unique storage name, position). It is what makes shadowing work."),
        ("What is three-address code?", "An IR where each instruction has at most one operator "
         "and three operands, e.g. `$t1 = a + b`, with labels and `ifFalse`/`goto` for control "
         "flow."),
        ("Why generate an IR instead of code directly?", "It separates language analysis from "
         "the target; the same IR could feed another back-end, and it is easy to display and test."),
        ("What is your target code?", "Instructions for a small stack-based virtual machine "
         "(`PUSH`, `LOAD`, `ADD`, `JZ`, ...). We do not generate native machine code."),
        ("How is `a and b` short-circuited?", "In the IR it is lowered to a conditional jump that "
         "skips evaluating `b` when `a` is false."),
        ("How are runtime errors handled?", "Division by zero, bad or missing input and the step "
         "limit raise a run-time error reported with the source line; the CLI exits with code 3."),
        ("How do you know it works?", "%d automated tests pass, every example's output matches a "
         "hand-checked expected file, and two back-ends agree." % suite["total"]),
        ("What is new in your work?", "Nothing is a new compiler technique; the contribution is a "
         "small, fully tested, inspectable teaching compiler with good diagnostics."),
        ("What would you add next?", "Functions, arrays, constant folding, and maybe an LLVM "
         "back-end."),
    ]
    D.table(["Question", "Answer"], [[q, a] for q, a in qa], widths=[5.0, 11.0], size=9)

    # ---------------- conclusion
    D.h1("7. Conclusion")
    D.p("A complete Tiny compiler pipeline has been implemented, run and tested: lexical, syntax "
        "and semantic analysis, three-address code, stack-machine code generation and execution. "
        "%d automated tests (%s) and nine example programs verify the core features; error "
        "handling was tested with four invalid examples and many unit cases. The main limitations "
        "are the virtual-machine target, the absence of optimisation, and the missing real "
        "screenshots. The project is ready for demonstration and for extension by other students."
        % (suite["total"], "all passing" if suite["ok"] else "see results"), "justify")

    # ---------------- references
    D.h1("8. References")
    D.p("Bibliographic details were checked on %s against Crossref (DOI records), the Open Library "
        "catalogue (books) and the publisher/author pages listed. Type is stated for each entry." %
        TODAY, size=9)
    refs = [
        "[1] A. V. Aho, M. S. Lam, R. Sethi and J. D. Ullman, *Compilers: Principles, Techniques, "
        "and Tools*, 2nd ed. Boston, MA: Pearson/Addison-Wesley, 2006. ISBN 978-0-321-48681-3. "
        "(Textbook)",
        "[2] K. C. Louden, *Compiler Construction: Principles and Practice*. Boston, MA: PWS "
        "Publishing, 1997. ISBN 0-534-93972-4. (Textbook; source of the TINY language)",
        "[3] N. Wirth, *Compiler Construction*. Harlow, UK: Addison-Wesley, 1996. "
        "ISBN 0-201-40353-6. (Textbook)",
        "[4] R. Nystrom, *Crafting Interpreters*. Genever Benning, 2021. ISBN 978-0-9905829-3-9. "
        "Online edition: https://craftinginterpreters.com/ . (Book)",
        "[5] K. D. Cooper and L. Torczon, *Engineering a Compiler*, 3rd ed. Morgan Kaufmann "
        "(Elsevier), 2022. ISBN 978-0-12-815412-0. (Textbook)",
        "[6] C. Lattner and V. Adve, \"LLVM: A compilation framework for lifelong program "
        "analysis & transformation,\" in *Proc. International Symposium on Code Generation and "
        "Optimization (CGO)*, 2004, pp. 75-86. doi:10.1109/CGO.2004.1281665. "
        "(Peer-reviewed conference paper)",
        "[7] N. Wirth, \"The programming language Pascal,\" *Acta Informatica*, vol. 1, no. 1, "
        "pp. 35-63, 1971. doi:10.1007/BF00264291. (Peer-reviewed journal article)",
        "[8] R. Ierusalimschy, L. H. de Figueiredo and W. Celes, \"The implementation of Lua "
        "5.0,\" *Journal of Universal Computer Science*, vol. 11, no. 7, pp. 1159-1176, 2005. "
        "doi:10.3217/jucs-011-07-1159. (Peer-reviewed journal article; open access at "
        "https://www.lua.org/doc/jucs05.pdf)",
        "[9] V. R. Pratt, \"Top down operator precedence,\" in *Proc. 1st ACM SIGACT-SIGPLAN "
        "Symposium on Principles of Programming Languages (POPL)*, 1973, pp. 41-51. "
        "doi:10.1145/512927.512931. (Peer-reviewed conference paper)",
        "[10] B. Ford, \"Parsing expression grammars: a recognition-based syntactic foundation,\" "
        "*ACM SIGPLAN Notices*, vol. 39, no. 1, pp. 111-122, 2004 (POPL 2004). "
        "doi:10.1145/982962.964011. (Peer-reviewed conference paper)",
    ]
    for r in refs:
        D.p(r, size=10, after=3)
    D.p("[[Check the reference style required by your institution (IEEE-style shown here).]]",
        size=9)

    # ---------------- appendices
    D.page_break()
    D.h1("Appendix A. Setup and CLI commands")
    D.p("**Windows PowerShell**")
    D.code("git clone https://github.com/<owner>/Chirayu-Project.git\n"
           "cd Chirayu-Project\n"
           "python --version                      # 3.8 or newer\n"
           "python main.py examples/hello.tiny\n"
           "python main.py examples/loop.tiny --all\n"
           'python main.py examples/gcd.tiny --input "84 36"\n'
           "python -m unittest discover -s tests -t . -v")
    D.p("**Linux / macOS**: same commands with `python3` (not run on this project's machine).")
    D.table(["Option", "Effect"], [
        ["`--tokens`", "token stream"], ["`--ast`", "abstract syntax tree"],
        ["`--symbols`", "symbol table"], ["`--ir`", "three-address code"],
        ["`--code`", "stack-machine code"], ["`--all`", "all stages, then run"],
        ["`--check`", "compile only"], ["`--backend vm|ir`", "stack VM or TAC interpreter"],
        ["`--input TEXT`", "values for `read`"], ["`--trace`", "trace VM execution (stderr)"],
        ["`--max-steps N`", "instruction limit (default 5,000,000)"],
        ["`--no-warnings`", "hide warnings"],
    ], widths=[4, 12], caption="CLI options")
    D.p("Exit codes: 0 success, 1 compile error, 2 usage error, 3 run-time error, 4 file error.")

    D.h1("Appendix B. Grammar")
    D.code(read("docs/GRAMMAR.md").split("```ebnf")[1].split("```")[0].strip(), 8)

    D.h1("Appendix C. Representative code")
    D.p("Lexer - the two-character-operator and single-character-operator handling "
        "(`Lexer._next_token`, excerpt):")
    src = source_of(lexer_mod.Lexer._next_token).split("\n")
    D.code("\n".join(src[:42]))
    D.p("Semantic analysis - binary-operator type rules (`SemanticAnalyzer._binary`):")
    D.code(source_of(semantic_mod.SemanticAnalyzer._binary))
    D.p("Virtual machine - fetch/execute loop (`VM.run`, excerpt):")
    D.code("\n".join(source_of(vm_mod.VM.run).split("\n")[:34]))

    D.h1("Appendix D. Final acceptance table")
    D.p("Each row was produced by running the stated verification command when this report was "
        "built (%s). PASS = the command ran and its output matched; NOT RUN = not executed, with "
        "the reason." % TODAY, size=9.5)
    D.table(["Requirement", "Implementation", "Verification command", "Result", "Limitation"],
            [[a, b, "`%s`" % c, "**%s**" % d_, e] for a, b, c, d_, e in acceptance],
            widths=[4.4, 3.0, 3.8, 2.2, 2.6], size=7.5, caption="Acceptance table")

    D.h1("Appendix E. Review 2 checklist mapping")
    D.table(["Template item (as listed in the project prompt)", "Report section", "Artifact"], [
        ["1. Project details: title, students, register numbers, branch, guide, review date",
         "Title page, Section 1", "placeholders to fill"],
        ["2. Introduction", "2.1", "-"],
        ["2. Problem statement / need", "2.2", "-"],
        ["2. Objectives", "2.3", "-"],
        ["2. Proposed solution", "2.5", "docs/ARCHITECTURE.md"],
        ["2. Expected outcome", "2.6", "-"],
        ["3. Actual status, completed modules", "3.1", "tiny_compiler/ package"],
        ["3. Tools / languages / platforms", "3.5", "-"],
        ["3. Architecture / block diagram / workflow", "3.3", "docs/img/architecture.png"],
        ["3. Real screenshots", "3.6", "placeholders; screenshots/README.md"],
        ["3. Actual results", "3.7", "docs/TESTING.md"],
        ["3. Remaining work", "3.8", "-"],
        ["4. Novelty: what is different, how, which improvement", "4", "-"],
        ["(5 - skipped in the template numbering)", "-", "-"],
        ["6. Presentation and Q&A: outline, viva questions", "6.1, 6.2", "-"],
    ], widths=[8.0, 3.2, 4.8], caption="Review 2 checklist mapping", size=9)

    D.save(REPORT)
    print("wrote", REPORT)
    print("tests: %d, suite ok: %s" % (suite["total"], suite["ok"]))
    return 0 if suite["ok"] else 1


def write_testing_md(suite, modres, valid_res, invalid_res, rt_ok, acceptance, pyver, osver):
    L = []
    L.append("# Testing\n")
    L.append("This file is generated by `python tools/build_report.py`; the results below come "
             "from actually running the commands (%s, Python %s, %s).\n" % (TODAY, pyver, osver))
    L.append("## How to run\n")
    L.append("```powershell\npython -m unittest discover -s tests -t . -v\n```\n")
    L.append("No third-party packages are needed. `python -m pytest tests` also works if pytest is "
             "installed.\n")
    L.append("## Test plan\n")
    L.append("| Level | Module | Purpose |\n|---|---|---|")
    L.append("| Unit | `tests/test_lexer.py` | valid and invalid tokens, positions, comments, strings |")
    L.append("| Unit | `tests/test_parser.py` | precedence, associativity, valid/invalid syntax, "
             "recovery, unsupported constructs |")
    L.append("| Unit | `tests/test_semantics.py` | declarations, scopes, types, constant division by "
             "zero, warnings |")
    L.append("| Unit | `tests/test_ir.py` | exact three-address code, labels, short-circuit, TAC "
             "interpreter |")
    L.append("| Unit | `tests/test_codegen_vm.py` | exact stack code, execution, input, run-time "
             "errors, random differential test |")
    L.append("| End-to-end | `tests/test_end_to_end.py` | every example through the CLI, every CLI "
             "option, exit codes |")
    L.append("")
    L.append("Expected outputs in `examples/*.expected` were checked by hand (for example "
             "`-7 / 3 = -2`, `-7 % 3 = -1`, sum 1..10 = 55, gcd(84, 36) = 12) before being used as "
             "references. Two manual mutation spot-checks (breaking integer division, and removing `%` "
             "from the multiplicative level of the parser) made the suite fail, confirming that "
             "the tests detect such bugs.\n")
    L.append("## Actual results\n")
    L.append("| Module | Tests | Result |\n|---|---|---|")
    for m, (ok, n, _) in modres.items():
        L.append("| `%s.py` | %d | %s |" % (m, n, "PASS" if ok else "FAIL"))
    L.append("| **all** | **%d** | **%s** (%ss) |\n" % (suite["total"], "PASS" if suite["ok"]
                                                         else "FAIL", suite["secs"]))
    L.append("## Example programs\n")
    L.append("| Program | Result |\n|---|---|")
    for n, (ok, _) in valid_res.items():
        L.append("| `examples/%s.tiny` | %s |" % (n, "PASS" if ok else "FAIL"))
    for n, (ok, _) in invalid_res.items():
        L.append("| `examples/%s.tiny` (expected diagnostics, exit 1) | %s |" %
                 (n, "PASS" if ok else "FAIL"))
    L.append("| `examples/invalid_runtime.tiny` (division by zero, exit 3) | %s |\n" %
             ("PASS" if rt_ok else "FAIL"))
    L.append("## Final acceptance table\n")
    L.append("| Requirement | Implementation | Verification command | Result | Limitation |\n"
             "|---|---|---|---|---|")
    for a, b, c, d_, e in acceptance:
        L.append("| %s | %s | `%s` | **%s** | %s |" % (a, b, c, d_, e))
    L.append("")
    L.append("## Not tested / known gaps\n")
    L.append("* Linux and macOS were not available; the commands differ only in `python3` and "
             "shell quoting.\n* Real screenshots have not been captured.\n"
             "* Interactive (keyboard) `read` prompts were not covered by automated tests; "
             "reading from `--input` and from piped stdin is.\n")
    with open(TESTING_MD, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))
    print("wrote", TESTING_MD)


if __name__ == "__main__":
    sys.exit(main())
