# Tiny Language Specification (version 1.0)

There is no single universal "TINY" language. The name is used for several small teaching
languages (the best-known one is the TINY language from K. Louden's *Compiler Construction:
Principles and Practice*). **This project defines its own small, C-like Tiny dialect** and
documents it completely here. The formal grammar is in [GRAMMAR.md](GRAMMAR.md).

## 1. Lexical structure

| Element | Rule |
|---|---|
| Whitespace | space, tab, CR, LF - ignored between tokens |
| Line comment | `// ...` up to end of line |
| Block comment | `/* ... */`, may span lines, does **not** nest; an unclosed one is an error |
| Identifier | `[A-Za-z_][A-Za-z0-9_]*`, case-sensitive |
| Integer literal | one or more decimal digits (`0`, `42`). A literal has no sign - `-5` is unary minus applied to `5`. A literal glued to letters (`12abc`) is a lexical error |
| String literal | `"..."` on a single line; escapes `\n` `\t` `\"` `\\`. Strings may **only** be used as items of a `write` statement |
| Keywords (reserved) | `var int bool if else while read write true false and or not` |
| Operators / punctuation | `+ - * / % < <= > >= == != = ( ) { } ; : ,` |

Any other character (for example `@`, `#`, `$`, `&`, `|`, `!` on its own, non-ASCII letters)
outside a string or comment is a **lexical error**; scanning then continues so that all such
characters are reported.

## 2. Types

| Type | Values | Notes |
|---|---|---|
| `int` | arbitrary-precision integers | the implementation uses Python integers, so there is no overflow |
| `bool` | `true`, `false` | produced by comparisons and logical operators |

There are no implicit conversions: an `int` is never a condition and a `bool` never takes part
in arithmetic. Strings are not a type; they are only literals inside `write`.

## 3. Declarations, scope and initial values

```
var name: int;            // initial value 0
var flag: bool;           // initial value false
var total: int = 3 * 4;   // with initialiser
```

* A variable must be declared before it is used (declaration order in the source).
* The declaration may appear anywhere a statement may appear, including inside blocks.
* **Block scope:** `{ ... }` (and the bodies of `if` / `else` / `while`) open a new scope. A
  variable is visible from its declaration to the end of the enclosing block, including nested
  blocks.
* Redeclaring a name in the **same** scope is an error. Declaring it in a **nested** scope
  *shadows* the outer variable until the end of that block.
* If a block later declares `x`, any use of `x` earlier in that block is an error ("used before
  its declaration") even if an outer `x` exists - it never silently binds to the outer variable.
* The initialiser is analysed before the new name is declared, so `var x: int = x + 1;` is an
  error.
* A declaration inside a loop body is executed (and the variable re-initialised) on every
  iteration.

## 4. Statements

| Statement | Meaning |
|---|---|
| `var x: T [= e];` | declaration (section 3) |
| `x = e;` | assignment; `e` must have the type of `x` |
| `if (c) { ... }` | conditional |
| `if (c) { ... } else { ... }` | two-way conditional |
| `if (c) { ... } else if (c2) { ... } else { ... }` | chain (syntactic sugar for nesting) |
| `while (c) { ... }` | loop; `c` is re-evaluated before each iteration |
| `{ ... }` | block / new scope |
| `read x;` | read one value into `x` (see section 6) |
| `write i1, i2, ...;` | print the items separated by one space, then a newline. An item is an expression or a string literal |

Conditions `c` must have type `bool`, and the parentheses and braces are mandatory.
There is no `for`, `break`, `continue`, function, array or float; these (and common
foreign keywords such as `print`, `elif`, `return`, `float`) are rejected with an explicit message.

## 5. Expressions

Precedence from **lowest** to **highest** binding:

| Level | Operators | Associativity | Operand types -> result |
|---|---|---|---|
| 1 | `or` | left | bool, bool -> bool |
| 2 | `and` | left | bool, bool -> bool |
| 3 | `not` | prefix (right) | bool -> bool |
| 4 | `==` `!=` `<` `<=` `>` `>=` | **non-associative** (`a < b < c` is a syntax error) | `<` `<=` `>` `>=`: int, int -> bool; `==` `!=`: T, T -> bool (same type) |
| 5 | `+` `-` | left | int, int -> int |
| 6 | `*` `/` `%` | left | int, int -> int |
| 7 | unary `-` | prefix (right) | int -> int |
| 8 | literals, variables, `( expr )` | - | - |

Notes

* `not a < b` means `not (a < b)` because `not` binds more loosely than comparison.
* `and` / `or` are **short-circuit**: the right operand is evaluated only when needed
  (`x != 0 and 10 / x > 1` never divides by zero).
* `/` is integer division **truncating toward zero**; `%` has the sign of the dividend, so that
  `(a / b) * b + a % b == a` always holds. `7 / 2 = 3`, `-7 / 2 = -3`, `-7 % 3 = -1`.
* Division or modulo by a divisor that is a compile-time constant zero
  (`5 / 0`, `5 % (3 - 3)`) is a **semantic error**; a zero divisor that is only known at run time
  is a **run-time error** (`division by zero`).

## 6. Input and output

* `write` evaluates each item left to right, prints `int` in decimal and `bool` as `true` /
  `false`, separates items with one space and ends with a newline. `write "";` prints just a
  newline.
* `read x;` takes the next whitespace-separated token from the input (standard input, or
  `--input "..."` on the command line). For an `int` variable the token must be an optionally
  signed decimal integer; for a `bool` it must be `true` or `false` (case-insensitive).
  Input that is exhausted or malformed is a run-time error.

## 7. Diagnostics

| Phase | Examples |
|---|---|
| lexical | invalid character, malformed number, unterminated string / block comment, bad escape |
| syntax | missing `;` `)` `}`, missing operand, chained comparison, body without braces, unsupported construct |
| semantic | undeclared / duplicate / used-before-declaration variable, type mismatch, non-`bool` condition, constant division by zero |
| runtime | division / modulo by zero, bad or missing input, step limit exceeded |
| warning | variable declared but its value is never read (only shown when there are no errors) |

Every compile-time diagnostic carries a 1-based line and column and is printed with the source
line and a caret. Lexical errors stop compilation before parsing; syntax errors stop it before
semantic analysis (the parser recovers at statement boundaries to report several syntax errors
per run).

## 8. Execution model

Programs are compiled to three-address code and then to stack-machine code that is executed by
the bundled virtual machine. **No native machine code is produced.** An execution is aborted
after `--max-steps` instructions (default 5,000,000) to stop infinite loops.
