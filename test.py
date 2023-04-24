from parser_edsl import *

E, T, F = map(NonTerminal, 'ETF')
number = Terminal('NUMBER', '[0-9]+', int)
E |= E, '+', T, lambda x, y: x + y
E |= T
T |= T, '*', F, lambda x, y: x * y
T |= F
F |= number
F |= '(', E, ')'
p = Parser(E)
p.add_skipped_domain('\\s')
p.add_skipped_domain('\\{.*?\\}')


def test(text):
    try:
        print('ОК:', p.parse(text))
    except Error as e:
        print(f'Ошибка {e.pos}:', e.message())


def title(message):
    print()
    print(message)
    print('-' * len(message))


title('Примеры успешного разбора:')
test('1')
test('1 {комментарий} + 2')
test('2 + 3*4*(5+6)')

title('Примеры синтаксических и лексических ошибок:')
test('2 + 3*4*(5+6)+')
test('2 + 3*4*(5+6))')
test('2 + 3*4*(5+6)1')
test('2 + 3*4*(5+6')
test('''
2 + 3*4
*(5@6)
'''.strip())
test('')

title('Токены:')
for token in p.get_tokens('3+{комментарий}*\n(  +100500)'):
    print(token.pos, ':', token)
