from collections import deque
from parser_edsl import ParsingTable
from initialize_grammar import digit
import inspect


"""
Lexer error exception.
"""


class LexerError(Exception):
    def __init__(self, pos):
        self.pos = pos

"""
Stack of states and inputs
Stack of variable attributes
"""
stack = deque()
attributes = deque()

"""
Parser structure:
gets input as array list of tokens
lr table state action goto
"""


class Token:
    def __init__(self, type):
        self.type = type

    def __str__(self):
        return 'Token %s' % self.type


class AttrToken(Token):
    def __init__(self, type, value):
        super().__init__(type)
        self.value = value

    def __str__(self):
        return 'AttrToken %s (%s)' % (self.type, str(self.value))


# Create token list manually for test
one = AttrToken('1', 1)
two = AttrToken('2', 2)
three = AttrToken(digit, 3)
plus = Token('+')
minus = Token('-')
end = Token('$end')
brace = Token('(')
bracer = Token(')')
tokens = [brace, two, minus, three, bracer, plus, one, end]


def next_token(i):
    return tokens[i]


def getNTerm(nonterms, param):
    for nt in nonterms:
        if nt.name == param:
            return nt
    raise RuntimeError()


def get_attr(cur):
    if isinstance(cur, AttrToken):
        attributes.append(cur.value)


def apply_func(lambda_func):
    # print("NUMBER OF ARGS ", inspect.getargspec(lambda_func))
    # print("NUMBER OF ARGS ", lambda_func.__code__.co_argcount)
    arguments_n = lambda_func.__code__.co_argcount
    if arguments_n == 2:
        t1 = attributes.pop()
        t2 = attributes.pop()
        res = lambda_func(t2, t1)
        attributes.append(res)
    elif arguments_n == 1:
        t1 = attributes.pop()
        res = lambda_func(t1)
        attributes.append(res)


class MyParser:
    def __init__(self, table):
        self.table: ParsingTable = table
        stack.append(0)
        for (idx, prod) in enumerate(self.table.grammar.productions):
            print(idx, prod)

    def parse(self):
        pos = 0
        cur = tokens[pos]
        while True:
            cur_state = stack[-1]
            action = list(self.table.action[cur_state][cur.type])
            if action[0][0] == "shift and go to state":
                get_attr(cur)
                stack.append(action[0][1])
                pos += 1
                cur = tokens[pos]
            elif action[0][0] == "reduce using rule":
                lambda_func = self.table.grammar.productions[action[0][1]][2]
                apply_func(lambda_func)
                n = len(self.table.grammar.productions[action[0][1]][1])
                for i in range(n):
                    stack.pop()
                goto_state = self.table.goto[stack[-1]][
                    getNTerm(self.table.nonterms, self.table.grammar.productions[action[0][1]][0])]
                stack.append(goto_state)
                pass
            elif action[0][0] == "accept":
                print("Attribute stack ", attributes)
                print("parsing is done: accept")
                break
