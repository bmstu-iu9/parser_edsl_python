import parser_edsl as pe

E = pe.NonTerminal('E')
T = pe.NonTerminal('T')
F = pe.NonTerminal('F')
N = pe.NonTerminal('N')
D = pe.NonTerminal('D')

digit = pe.Terminal('[0-9]+', int)

E |= T, '+', T, lambda t1, t2: t1 + t2
E |= T
E |= T, '-', T, lambda t1, t2: t1 - t2
T |= F, '*', F, lambda f1, f2: f1 * f2
T |= F, '/', F, lambda f1, f2: f1 / f2
T |= F
F |= N
F |= '(', E, ')'
N |= D
N |= D, D
D |= '0'
D |= '1'
D |= '2'
D |= digit
pe.nonTerminals.append(E)
pe.nonTerminals.append(T)
pe.nonTerminals.append(F)
pe.nonTerminals.append(N)
pe.nonTerminals.append(D)


# parser = pe.Parser()
#
# E = parser.non_terminal('E')
# digit = parser.terminal('digit', '[0-9]+', int)
# kwmod = parser.terminal('kwmod', 'mod')  # Ключевое слово mod атрибут None
# ident = parser.terminal('ident', '[A-Za-z][A-Za-z0-9]*', str)
# parser.terminal('comment', '#.*', 'SKIP')
# parser.terminal('comment', '#.*', pe.SKIP)  # или так
# parser.terminal('whitespace', '\\s', pe.SKIP)
#
# x = parser.parse_string('2 mod 3 + x')
# y = parser.parse_file('expression.txt')

'''
re компилировать лучше в режиме multiline \A - от начала строки
по очереди для кажд терм символа матчить с терминалами, добавляя \А выбираем вариант с наибольшей длиной кот указан раньше
'''
