import math
import re
from parser_edsl import *


# Словарь констант (понадобится в примере)
CONSTANTS = {
    'pi': math.pi,
    'e': math.e,
    'Na': 6.02214076e23, # Постоянная Больцмана
    'kB': 1.380649e-23, # Число Авогадро
}


# ZeroDiv и checked_div нужны для примера учёта координат в действиях

class ZeroDiv(Error):
    def __init__(self, pos):
        self.pos = pos

    @property
    def message(self):
        return 'Деление на нуль (или ноль)'


def checked_div(values, coords, res_coord):
    x, y = values
    cx, cdiv, cy = coords

    if y != 0:
        return x / y
    else:
        raise ZeroDiv(cy)


# Определения нетерминальных символов
Expr = NonTerminal('Expr')
Term = NonTerminal('Term')
Factor = NonTerminal('Factor')

# Определения терминальных символов

# Строка из десятичных цифр подходит под оба регулярных выражения,
# поэтому для целых чисел повышаем приоритет (по умолчанию — 5)
integer = Terminal('INTEGER', '[0-9]+', int, priority=7)
real = Terminal('REAL', '[0-9]+(\\.[0-9]*)?([eE][-+]?[0-9]+)?', float)

# Ключевое слово без учёта регистра (тоже повышаем приоритет)
kw_mod = Terminal('MOD', 'mod', lambda x: None,
                  re_flags=re.IGNORECASE, priority=10)
const = Terminal('CONST', '[A-Za-z]+', str)

# Определение правил грамматики
Expr |= Expr, '+', Term, lambda x, y: x + y
Expr |= Expr, '-', Term, lambda x, y: x - y
Expr |= Term
Term |= Term, '*', Factor, lambda x, y: x * y
Term |= Term, '/', Factor, ExAction(checked_div) # Деление с проверкой
Term |= Term, kw_mod, Factor, lambda x, y: x % y
Term |= Factor
Factor |= integer
Factor |= real
Factor |= const, lambda name: CONSTANTS[name]
Factor |= '(', Expr, ')'

# Создаём парсер и проверяем грамматику на LALR(1)
p = Parser(Expr)
assert p.is_lalr_one()

# Игнорируем пробельные символы и комментарии вида {...}
p.add_skipped_domain('\\s')
p.add_skipped_domain('\\{.*?\\}')


# Тесты

def test(text):
    try:
        print('ОК:', p.parse(text))
    except Error as e:
        print(f'Ошибка {e.pos}: {e.message}')


def title(message):
    print()
    print(message)
    print('-' * len(message))


title('Примеры успешного разбора:')
test('1')
test('1 {комментарий} + 2')
test('2 + 3.5*4/(76-6)')
test('1e+2 + 1e-2')
test('100 mod 7')
test('100 Mod 7')
test('100 MOD 7')
test('pi + e')
test('kB * Na')

title('Примеры синтаксических и лексических ошибок:')
test('2 + 3.5*4/(76-6)+')
test('2 + 3.5*4/(76-6))')
test('2 + 3.5*4/(76-6)1')
test('2 + 3.5*4/(76-6')
test('''
2 + 3*4
*(5@6)
'''.strip())
test('')
test('2 + 3.5*4/(76-76)')

title('Токены:')
for token in p.get_tokens('3e8+{комментарий}*\n(  /-100500mod100.500)'):
    print(token.pos, ':', token)


# Пример отладки не-LALR(1)-грамматики — у неё is_lalr_one() вернёт False,
# в отладочной печати таблицы можно наблюдать конфликты

title('Пример на не-LALR(1)-грамматику:')

pal = NonTerminal('palindrome')
pal |= 'a'
pal |= 'a', pal, 'a'
pal_par = Parser(pal)

print('Грамматика палиндромов LALR(1)?', pal_par.is_lalr_one())
print()
print('Таблица грамматики палиндромов:')
pal_par.print_table()


# Пример на работу с пустыми правилами

title('Работа с пустой грамматикой:')
Empty = NonTerminal('Empty')
Empty |= ()
parser_empty = Parser(Empty)
print(parser_empty.parse(''))

try:
    parser_empty.parse('x')
except Error as e:
    print(e.pos, e.message)
