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

    with pytest.raises(RuntimeError):
        result = parser.parse_earley("42+3-5")