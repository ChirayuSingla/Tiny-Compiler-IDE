# Tiny Grammar

The grammar is LL(1)-friendly and is implemented one-to-one by the recursive-descent parser in
`tiny_compiler/parser.py` (one method per non-terminal). Notation: `{ x }` = zero or more,
`[ x ]` = optional, `|` = alternative, quoted text = terminal token.

```ebnf
program        = { statement } ;

statement      = var_decl | assignment | if_stmt | while_stmt
               | read_stmt | write_stmt | block ;

var_decl       = "var" IDENT ":" type [ "=" expression ] ";" ;
type           = "int" | "bool" ;
assignment     = IDENT "=" expression ";" ;
if_stmt        = "if" "(" expression ")" block
                 [ "else" ( if_stmt | block ) ] ;
while_stmt     = "while" "(" expression ")" block ;
read_stmt      = "read" IDENT ";" ;
write_stmt     = "write" write_item { "," write_item } ";" ;
write_item     = STRING | expression ;
block          = "{" { statement } "}" ;

expression     = or_expr ;
or_expr        = and_expr  { "or"  and_expr } ;
and_expr       = not_expr  { "and" not_expr } ;
not_expr       = "not" not_expr | comparison ;
comparison     = additive [ rel_op additive ] ;          (* at most one: non-associative *)
rel_op         = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
additive       = term { ( "+" | "-" ) term } ;
term           = unary { ( "*" | "/" | "%" ) unary } ;
unary          = "-" unary | primary ;
primary        = INT | "true" | "false" | IDENT | "(" expression ")" ;
```

Lexical terminals

```ebnf
IDENT   = ( letter | "_" ) { letter | digit | "_" } ;      (* not a keyword *)
INT     = digit { digit } ;
STRING  = '"' { character - '"' - newline | escape } '"' ;
escape  = "\n" | "\t" | '\"' | "\\" ;
comment = "//" { any - newline }  |  "/*" { any } "*/" ;
```

Keywords: `var int bool if else while read write true false and or not`.

## Design notes

* Precedence is encoded by the layering of the non-terminals (loosest first: `or`, `and`,
  `not`, comparison, additive, term, unary, primary). Left associativity of `+ - * / % and or`
  comes from the `{ ... }` loops that build the tree left-deep.
* The dangling-`else` ambiguity does not exist because every branch body is a braced block.
* `comparison` allows a single relational operator; a second one is reported as
  "comparison operators cannot be chained".
* A `STRING` is accepted only as a `write_item`; a string in an expression position is rejected.
* **Error recovery:** after a syntax error the parser skips tokens until just after the next
  `;` (or to a `}` / statement keyword) and continues. A statement that is only missing its `;`
  does not swallow the next statement.
* Words such as `for`, `print`, `elif`, `return`, `float` lex as ordinary identifiers; the
  parser recognises them at the start of a statement (or as a type) and reports that they are not
  supported, instead of a confusing generic error.

## Derivation example

`x = 1 + 2 * 3;`

```
statement -> assignment -> IDENT "=" expression ";"
expression -> or_expr -> and_expr -> not_expr -> comparison -> additive
additive   -> term "+" term
term(1)    -> unary -> primary -> INT(1)
term(2)    -> unary "*" unary -> INT(2) "*" INT(3)
```

giving the tree `Binary '+'( IntLit 1, Binary '*'( IntLit 2, IntLit 3 ) )`.
