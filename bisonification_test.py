import pytest
import parser_edsl as pe

@pytest.mark.parametrize(
    "text, attr", [
        ("2+2*2+2", 8),
        ("2*2+2*2", 8),
        ("10+100*2", 210)
    ]
)
def test_parse_priority_1(text, attr):
    expr = pe.NonTerminal('expr')
    expr |= (expr, '+',  expr, pe.Left(1), lambda a, b: a + b)
    expr |= (expr, '*',  expr, pe.Left(20), lambda a, b: a * b)
    expr |= (pe.Terminal('NUM', r'\d+', int), lambda x: x)

    parser = pe.Parser(expr)

    assert parser.parse(text) == attr

@pytest.mark.parametrize(
    "text, attr", [
        ("2+2*2+2", 16),
        ("2*2+2*2", 16),
        ("10+100*2", 220)
    ]
)
def test_parse_priority_2(text, attr):
    expr = pe.NonTerminal('expr')
    expr |= (expr, '+',  expr, pe.Left(20), lambda a, b: a + b)
    expr |= (expr, '*',  expr, pe.Left(1), lambda a, b: a * b)
    expr |= (pe.Terminal('NUM', r'\d+', int), lambda x: x)

    parser = pe.Parser(expr)

    assert parser.parse(text) == attr


@pytest.mark.parametrize(
    "text, attr", [
        ("100-10-10", 80),
        ("2^3^2", 64),
        ("100-10^2", 8100)
    ]
)
def test_parse_left_assoc(text, attr):
    expr = pe.NonTerminal('expr')
    expr |= (expr, '-',  expr, pe.Left(20), lambda a, b: a - b)
    expr |= (expr, '^',  expr, pe.Left(1), lambda a, b: a ** b)
    expr |= (pe.Terminal('NUM', r'\d+', int), lambda x: x)

    parser = pe.Parser(expr)

    assert parser.parse(text) == attr

@pytest.mark.parametrize(
    "text, attr", [
        ("100-10-10", 100),
        ("2^3^2", 512),
        ("100-10^2", 8100)
    ]
)
def test_parse_right_assoc(text, attr):
    expr = pe.NonTerminal('expr')
    expr |= (expr, '-',  expr, pe.Right(20), lambda a, b: a - b)
    expr |= (expr, '^',  expr, pe.Right(1), lambda a, b: a ** b)
    expr |= (pe.Terminal('NUM', r'\d+', int), lambda x: x)

    parser = pe.Parser(expr)

    assert parser.parse(text) == attr
