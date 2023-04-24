import re
from parser_edsl import *


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


E, T, F = map(NonTerminal, 'ETF')
integer = Terminal('INTEGER', '[0-9]+', int, priority=7)
real = Terminal('REAL', '[0-9]+(\\.[0-9]*)?([eE][-+]?[0-9]+)?', float)
kw_mod = Terminal('MOD', 'mod', lambda x: None,
                  re_flags=re.IGNORECASE, priority=10)
E |= E, '+', T, lambda x, y: x + y
E |= E, '-', T, lambda x, y: x - y
E |= T
T |= T, '*', F, lambda x, y: x * y
T |= T, '/', F, ExAction(checked_div)
T |= T, kw_mod, F, lambda x, y: x % y
T |= F
F |= integer
F |= real
F |= '(', E, ')'
p = Parser(E)
assert p.is_lalr_one()
p.add_skipped_domain('\\s')
p.add_skipped_domain('\\{.*?\\}')


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

title('Пример на не-LALR(1)-грамматику:')

pal = NonTerminal('palindrome')
pal |= 'a'
pal |= 'a', pal, 'a'
pal_par = Parser(pal)

print('Грамматика палиндромов LALR(1)?', pal_par.is_lalr_one())
print()
print('Таблица грамматики палиндромов:')
pal_par.print_table()
