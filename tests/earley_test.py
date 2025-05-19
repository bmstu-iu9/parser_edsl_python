import pytest
import parser_edsl as pe

def test_defiened_grammar():
    expr = pe.NonTerminal('expr')
    texpr = pe.NonTerminal('texpr')
    expr |= (expr, '+', texpr, lambda a, b: a + b)
    expr |= (expr, '-', texpr, lambda a, b: a - b)
    expr |= (texpr, lambda a: a)
    texpr |= (pe.Terminal('NUM', r'\d+', int), lambda x: x)

    parser = pe.Parser(expr)

    assert parser.parse_earley("42+3-5") == 40

def test_undefiened_grammar():
    expr = pe.NonTerminal('expr')
    expr |= (expr, '+', expr, lambda a, b: a + b)
    expr |= (expr, '-', expr, lambda a, b: a - b)
    expr |= (pe.Terminal('NUM', r'\d+', int), lambda x: x)

    parser = pe.Parser(expr)

    with pytest.raises(pe.ParseError):
        result = parser.parse_earley("42+3-5")


def test_epsilon_rule_empty_grammar():
    expr = pe.NonTerminal('expr')
    expr |= ()

    parser = pe.Parser(expr)

    assert parser.parse_earley("") == None


def test_epsilon_rule():
    expr = pe.NonTerminal('expr')
    expr |= ('a', expr, lambda _: None)
    expr |= (lambda: None)

    parser = pe.Parser(expr)

    assert parser.parse_earley("aaa") == None


def test_epsilon_rule_attrs():
    NAr = pe.NonTerminal("NAr")
    ARRAY = pe.Terminal("array", "array", lambda _: None, priority=10)

    NAr |= ARRAY, NAr, lambda x: x + 1
    NAr |= lambda: 0

    p = pe.Parser(NAr)
    p.add_skipped_domain("\\s")

    assert p.parse_earley("array  array") == 2
    assert p.parse_earley("  ") == 0
