import pytest
import parser_edsl as pe

def number_action(a):
        if int(a) > 100:
             raise pe.TokenAttributeError('Слишком большое значение: ' + a)
        return int(a)

@pytest.mark.parametrize(
    "text, message, offset, line, col", [
        ("10+300-5", "Слишком большое значение: 300", 3, 1, 4),
        ("100+500-5", "Слишком большое значение: 500", 4, 1, 5),
        ("1000+2000-5", "Слишком большое значение: 1000", 0, 1, 1),
    ]
)
def test_token_attribute_error(text, message, offset, line, col):
    expr = pe.NonTerminal('expr')
    expr |= (expr, pe.LiteralTerminal('+'), expr, lambda a, b: a + b)
    expr |= (expr, pe.LiteralTerminal('-'), expr, lambda a, b: a - b)
    expr |= (pe.Terminal('NUM', r'\d+', number_action), lambda x: x)
    parser = pe.Parser(expr)

    with pytest.raises(pe.ParseError) as parse_error:
           parser.parse(text)

    assert parse_error.value.message == message
    assert parse_error.value.pos == pe.Position(offset, line, col)
