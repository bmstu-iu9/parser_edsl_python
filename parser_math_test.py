import pytest
import parser_edsl as pe
import re
import math

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "Na": 6.02214076e23,  # Постоянная Больцмана
    "kB": 1.380649e-23,  # Число Авогадро
}

# Определения нетерминальных символов
Expr = pe.NonTerminal("Expr")
Term = pe.NonTerminal("Term")
Factor = pe.NonTerminal("Factor")


class ZeroDiv(pe.Error):
    def __init__(self, pos):
        self.pos = pos

    @property
    def message(self):
        return "Деление на нуль (или ноль)"


def checked_div(values, coords, res_coord):
    x, y = values
    cx, cdiv, cy = coords

    if y != 0:
        return x / y
    else:
        raise ZeroDiv(cy)


# Определения терминальных символов

# Строка из десятичных цифр подходит под оба регулярных выражения,
# поэтому для целых чисел повышаем приоритет (по умолчанию — 5)
integer = pe.Terminal("INTEGER", "[0-9]+", int, priority=7)
real = pe.Terminal("REAL", "[0-9]+(\\.[0-9]*)?([eE][-+]?[0-9]+)?", float)

# Ключевое слово без учёта регистра (тоже повышаем приоритет)
kw_mod = pe.Terminal("MOD", "mod", lambda x: None, re_flags=re.IGNORECASE, priority=10)
const = pe.Terminal("CONST", "[A-Za-z]+", str)

# Определение правил грамматики
Expr |= Expr, "+", Term, lambda x, y: x + y
Expr |= Expr, "-", Term, lambda x, y: x - y
Expr |= Term
Term |= Term, "*", Factor, lambda x, y: x * y
Term |= Term, "/", Factor, pe.ExAction(checked_div)  # Деление с проверкой
Term |= Term, kw_mod, Factor, lambda x, y: x % y
Term |= Factor
Factor |= integer
Factor |= real
Factor |= const, lambda name: CONSTANTS[name]
Factor |= "(", Expr, ")"


def test_is_lalr():
    # Создаём парсер и проверяем грамматику на LALR(1)
    p = pe.Parser(Expr)
    assert p.is_lalr_one()


@pytest.mark.parametrize(
    "text, attr",
    [
        ("1", 1),
        ("1 {комментарий} + 2", 3),
        ("2 + 3.5*4/(76-6)", 2.2),
        ("1e+2 + 1e-2", 100.01),
        ("100 mod 7", 2),
        ("100 Mod 7", 2),
        ("100 MOD 7", 2),
        ("pi + e", 5.859874),
        ("kB * Na", 8.314463),
    ],
)
def test_parse_ok(text, attr):
    p = pe.Parser(Expr)
    p.add_skipped_domain("\\s")
    p.add_skipped_domain("\\{.*?\\}")
    try:
        assert round(p.parse(text), 6) == attr
    except pe.Error as e:
        pytest.fail(f"Ошибка разбора: {e}")


@pytest.mark.parametrize(
    "text, error",
    [
        (
            "2 + 3.5*4/(76-6)+",
            "Неожиданный символ EOF, ожидалось CONST, '(', REAL, INTEGER",
        ),
        ("2 + 3.5*4/(76-6))", "Неожиданный символ ')', ожидалось '-', '+', EOF"),
        (
            "2 + 3.5*4/(76-6)1",
            "Неожиданный символ INTEGER(1), ожидалось '/', ')', MOD, '-', '*', '+', EOF",
        ),
        ("2 + 3.5*4/(76-6", "Неожиданный символ EOF, ожидалось ')', '-', '+'"),
    ],
)
def test_parse_not_ok(text, error):
    p = pe.Parser(Expr)
    p.add_skipped_domain("\\s")
    p.add_skipped_domain("\\{.*?\\}")
    with pytest.raises(pe.ParseError) as parseError:
        p.parse(text)
    assert parseError.value.message == error
