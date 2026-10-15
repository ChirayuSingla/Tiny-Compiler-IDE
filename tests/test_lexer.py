import unittest

from tests.helpers import tokenize, DiagnosticBag


def lex(src):
    bag = DiagnosticBag()
    toks = tokenize(src, bag)
    return toks, bag


def types(src):
    toks, bag = lex(src)
    assert not bag.has_errors(), [d.message for d in bag.errors]
    return [t.type for t in toks]


class ValidTokenTests(unittest.TestCase):
    def test_empty_source_is_just_eof(self):
        self.assertEqual(types(""), ["EOF"])

    def test_keywords_are_distinguished_from_identifiers(self):
        self.assertEqual(types("var int bool if else while read write true false and or not"),
                         ["var", "int", "bool", "if", "else", "while", "read", "write",
                          "true", "false", "and", "or", "not", "EOF"])
        self.assertEqual(types("variable iff whiles"), ["IDENT", "IDENT", "IDENT", "EOF"])

    def test_identifier_forms(self):
        toks, _ = lex("x _tmp Count2 a_b_c")
        self.assertEqual([t.lexeme for t in toks[:-1]], ["x", "_tmp", "Count2", "a_b_c"])
        self.assertTrue(all(t.type == "IDENT" for t in toks[:-1]))

    def test_integer_literal_value(self):
        toks, _ = lex("0 42 1234567890123456789012")
        self.assertEqual([t.value for t in toks[:-1]], [0, 42, 1234567890123456789012])
        self.assertTrue(all(t.type == "INT" for t in toks[:-1]))

    def test_operators_and_punctuation(self):
        src = "+ - * / % < <= > >= == != = ( ) { } ; : ,"
        self.assertEqual(types(src), src.split() + ["EOF"])

    def test_two_char_operators_win_over_one_char(self):
        self.assertEqual(types("a<=b"), ["IDENT", "<=", "IDENT", "EOF"])
        self.assertEqual(types("a==b"), ["IDENT", "==", "IDENT", "EOF"])
        self.assertEqual(types("a=b"), ["IDENT", "=", "IDENT", "EOF"])
        self.assertEqual(types("a!=b"), ["IDENT", "!=", "IDENT", "EOF"])

    def test_no_spaces_needed(self):
        self.assertEqual(types("x=1+2*3;"),
                         ["IDENT", "=", "INT", "+", "INT", "*", "INT", ";", "EOF"])

    def test_string_literal_with_escapes(self):
        toks, bag = lex(r'"a\tb\n\"q\" \\"')
        self.assertFalse(bag.has_errors())
        self.assertEqual(toks[0].type, "STRING")
        self.assertEqual(toks[0].value, 'a\tb\n"q" ' + chr(92))

    def test_line_comment_is_skipped(self):
        self.assertEqual(types("x // ignore = 5 @@\ny"), ["IDENT", "IDENT", "EOF"])

    def test_block_comment_is_skipped_across_lines(self):
        toks, bag = lex("x /* a\n b */ y")
        self.assertFalse(bag.has_errors())
        self.assertEqual([t.lexeme for t in toks[:-1]], ["x", "y"])
        self.assertEqual(toks[1].line, 2)

    def test_division_is_not_a_comment(self):
        self.assertEqual(types("a / b"), ["IDENT", "/", "IDENT", "EOF"])


class PositionTests(unittest.TestCase):
    def test_line_and_column_are_one_based(self):
        toks, _ = lex("var x;\n  y = 10;")
        got = [(t.lexeme, t.line, t.col) for t in toks[:-1]]
        self.assertEqual(got, [("var", 1, 1), ("x", 1, 5), (";", 1, 6),
                               ("y", 2, 3), ("=", 2, 5), ("10", 2, 7), (";", 2, 9)])

    def test_eof_position(self):
        toks, _ = lex("x\n")
        self.assertEqual((toks[-1].type, toks[-1].line, toks[-1].col), ("EOF", 2, 1))

    def test_position_after_block_comment(self):
        toks, _ = lex("/* c\nc */ z")
        self.assertEqual((toks[0].line, toks[0].col), (2, 6))


class LexicalErrorTests(unittest.TestCase):
    def test_invalid_character_reported_with_position(self):
        toks, bag = lex("x = 5 @ 3;")
        self.assertEqual(len(bag.errors), 1)
        d = bag.errors[0]
        self.assertEqual((d.phase, d.line, d.col), ("lexical", 1, 7))
        self.assertIn("invalid character '@'", d.message)

    def test_scanning_continues_after_invalid_character(self):
        toks, bag = lex("a $ b # c")
        self.assertEqual(len(bag.errors), 2)
        self.assertEqual([t.lexeme for t in toks[:-1]], ["a", "b", "c"])

    def test_single_ampersand_and_pipe_and_bang_have_hints(self):
        _, bag = lex("a & b | c ! d")
        msgs = [d.message for d in bag.errors]
        self.assertEqual(len(msgs), 3)
        self.assertIn("'and'", msgs[0])
        self.assertIn("'or'", msgs[1])
        self.assertIn("'!='", msgs[2])

    def test_non_ascii_character_is_invalid(self):
        _, bag = lex("x = \u00e9;")
        self.assertEqual(len(bag.errors), 1)

    def test_number_followed_by_letters_is_malformed(self):
        _, bag = lex("x = 12abc;")
        self.assertEqual(len(bag.errors), 1)
        self.assertIn("malformed number '12abc'", bag.errors[0].message)

    def test_unterminated_string(self):
        _, bag = lex('write "abc;\nx = 1;')
        self.assertEqual(len(bag.errors), 1)
        self.assertIn("unterminated string", bag.errors[0].message)
        self.assertEqual((bag.errors[0].line, bag.errors[0].col), (1, 7))

    def test_unterminated_block_comment(self):
        _, bag = lex("x = 1; /* never closed")
        self.assertEqual(len(bag.errors), 1)
        self.assertIn("unterminated block comment", bag.errors[0].message)
        self.assertEqual(bag.errors[0].col, 8)

    def test_unknown_escape_sequence(self):
        _, bag = lex(r'write "a\qb";')
        self.assertEqual(len(bag.errors), 1)
        self.assertIn("unknown escape sequence '" + chr(92) + "q'", bag.errors[0].message)


if __name__ == "__main__":
    unittest.main()
