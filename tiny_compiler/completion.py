"""Grammar-scoped completion and hover descriptions. No source is executed here."""
from dataclasses import dataclass
import re

from .lexer import tokenize, EOF, KEYWORDS
from .diagnostics import DiagnosticBag

HELP = {
    "var": "Declare a variable: var name: int = 0; or var flag: bool;",
    "int": "Integer type. Arithmetic uses integer division truncated toward zero.",
    "bool": "Boolean type: true or false.",
    "if": "Conditional statement: if (boolean) { statements } else { statements }",
    "else": "Optional alternative immediately following an if block.",
    "while": "Loop while a bool condition is true: while (condition) { statements }",
    "read": "Input statement: read declared_variable; accepts an int or bool token.",
    "write": "Output statement: write expression, \"text\"; prints a line.",
    "true": "Boolean literal true.", "false": "Boolean literal false.",
    "and": "Boolean AND with short-circuit evaluation.",
    "or": "Boolean OR with short-circuit evaluation.", "not": "Unary boolean negation.",
}
TEMPLATES = {
    "var": "var name: int = 0;",
    "if": "if (true) {\n    \n}",
    "if / else": "if (true) {\n    \n} else {\n    \n}",
    "while": "while (false) {\n    \n}",
    "read": "read name;",
    "write": 'write "message";',
}


@dataclass(frozen=True)
class Suggestion:
    label: str
    text: str
    description: str = ""


def lexical_state(text):
    state = "code"
    i = 0
    while i < len(text):
        ch, pair = text[i], text[i:i + 2]
        if state == "line":
            if ch == "\n":
                state = "code"
        elif state == "block":
            if pair == "*/":
                state = "code"
                i += 1
        elif state == "string":
            if ch == "\\":
                i += 1
            elif ch == '"':
                state = "code"
        elif pair in ("//", "/*"):
            state = "line" if pair == "//" else "block"
            i += 1
        elif ch == '"':
            state = "string"
        i += 1
    return state


def in_comment_or_string(text):
    return lexical_state(text) != "code"


def visible_symbols(source, position, table):
    """Use real analyzer symbols and current lexical scope/declaration identity.

    An older analysis may supply candidates only while the exact declaration
    still exists before the cursor with the same type, position and scope.
    """
    if table is None:
        return []
    tokens = [t for t in tokenize(source[:position]) if t.type != EOF]
    path = []
    declarations = {}
    for index, token in enumerate(tokens):
        if token.type == "{":
            path.append((token.line, token.col))
        elif token.type == "}":
            if path:
                path.pop()
        elif token.type == "var" and index + 3 < len(tokens):
            name, colon, typ = tokens[index + 1:index + 4]
            if name.type == "IDENT" and colon.type == ":" and typ.type in ("int", "bool"):
                declarations[(name.lexeme, name.line, name.col, typ.type)] = tuple(path)
    current = tuple(path)
    selected = {}
    for symbol in table.all_symbols:
        scope = declarations.get((symbol.name, symbol.line, symbol.col, symbol.type))
        if scope is not None and current[:len(scope)] == scope:
            previous = selected.get(symbol.name)
            if previous is None or symbol.depth > previous.depth:
                selected[symbol.name] = symbol
    return sorted(selected.values(), key=lambda s: s.name)


def completion_prefix(source, position):
    match = re.search(r"[A-Za-z_][A-Za-z_0-9]*$", source[:position])
    return match.group() if match else ""


def permits_else(tokens):
    if not tokens or tokens[-1].type != "}":
        return False
    depth = 0
    start = None
    for i in range(len(tokens) - 1, -1, -1):
        if tokens[i].type == "}":
            depth += 1
        elif tokens[i].type == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    if start is None or start == 0 or tokens[start - 1].type != ")":
        return False
    depth = 0
    for i in range(start - 1, -1, -1):
        if tokens[i].type == ")":
            depth += 1
        elif tokens[i].type == "(":
            depth -= 1
            if depth == 0:
                return i > 0 and tokens[i - 1].type == "if"
    return False


def suggestions(source, position, table=None, templates=True):
    before = source[:position]
    if in_comment_or_string(before):
        return []
    prefix = completion_prefix(source, position)
    context = before[:-len(prefix)] if prefix else before
    diagnostics = DiagnosticBag()
    tokens = [t for t in tokenize(context, diagnostics) if t.type != EOF]
    if diagnostics.has_errors():
        return []
    previous = tokens[-1].type if tokens else None
    symbols = visible_symbols(source, position, table)
    names = [s.name for s in symbols]
    types = {s.name: s.type for s in symbols}
    boundary = max((i for i, t in enumerate(tokens) if t.type in (";", "{", "}")), default=-1)
    statement_tokens = tokens[boundary + 1:]
    if len(statement_tokens) >= 2 and statement_tokens[0].type == "var":
        # A declared name is not in scope within its own initializer.
        names = [name for name in names if name != statement_tokens[1].lexeme]
    candidates = []
    statement = previous in (None, ";", "{", "}")
    if previous == ":":
        words = ["int", "bool"]
    elif previous == "var":
        words = []  # A fresh user-chosen identifier is required.
    elif previous == "read":
        words = names
    elif statement:
        words = ["var", "if", "while", "read", "write"] + names
        if permits_else(tokens):
            words.append("else")
    elif previous == "else":
        words = ["if", "{"]
    elif len(tokens) >= 2 and tokens[-2].type == "var" and previous == "IDENT":
        words = [":"]
    elif previous in ("int", "bool"):
        words = ["=", ";"]
    elif previous in ("=", "(", ",", "write", "+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "and", "or", "not"):
        words = names + ["true", "false", "not"]
        if previous in ("if", "while"):
            words = ["("]
    elif previous in ("if", "while"):
        words = ["("]
    elif previous in ("IDENT", "INT", "true", "false", ")", "STRING"):
        if previous == "IDENT" and (len(tokens) == 1 or tokens[-2].type in (";", "{", "}")):
            words = ["="] if tokens[-1].lexeme in names else []
        elif previous in ("true", "false") or (previous == "IDENT" and types.get(tokens[-1].lexeme) == "bool"):
            words = ["and", "or", "==", "!=", ")", ";", ","]
        elif previous == "STRING":
            words = [",", ";"]
        else:
            words = ["+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", ")", ";", ","]
    else:
        words = []
    for word in words:
        if word.startswith(prefix):
            description = HELP.get(word, "%s variable" % types[word] if word in types else "Tiny syntax")
            candidates.append(Suggestion(word, word, description))
    if statement and templates:
        for label, text in TEMPLATES.items():
            if label.startswith(prefix):
                candidates.append(Suggestion(label + "  [template]", text, "Editable statement template; does not execute code"))
    return candidates
