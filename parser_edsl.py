"""Библиотека для построения синтаксических анализаторов (LALR(1), LL(1), Earley).

Поддерживает:
- LALR(1) разбор с приоритетами и ассоциативностью операторов
- LL(1) предиктивный разбор
- Алгоритм Эрли для произвольных КС-грамматик
- Семантические действия через ExAction и простые лямбды
- Пользовательские лексические ошибки
"""

import abc
import collections
import dataclasses
import re
import sys
import warnings


__all__ = '''
Terminal
LiteralTerminal
ExAction
NonTerminal
EOF_SYMBOL
Position
Fragment
Parser
Error
ParseError
NonAssocError
EarleyAmbiguityError
LL1Error
Left
Right
NonAssoc
Prio
LALR1
LL1
EARLEY
EarleyItem
LexerUserError
TokenAttributeError
'''.split()


# ============== Константы методов парсинга ==============

class ParsingMethod:
    pass


class _LALR1(ParsingMethod):
    def __repr__(self):
        return 'LALR1'


class _LL1(ParsingMethod):
    def __repr__(self):
        return 'LL1'


class _EARLEY(ParsingMethod):
    def __init__(self, ambiguity='warn'):
        """
        Args:
            ambiguity: Поведение при обнаружении неоднозначности:
                'warn' — предупреждение + возврат одного результата (по умолчанию)
                'error' — поднять EarleyAmbiguityError
        """
        self.ambiguity = ambiguity

    def __repr__(self):
        return 'EARLEY'


LALR1 = _LALR1()
LL1 = _LL1()
EARLEY = _EARLEY()


# ============== Приоритет и ассоциативность ==============

@dataclasses.dataclass(frozen=True)
class Left:
    """Левая ассоциативность с указанным приоритетом"""
    priority: int


@dataclasses.dataclass(frozen=True)
class Right:
    """Правая ассоциативность с указанным приоритетом"""
    priority: int


@dataclasses.dataclass(frozen=True)
class NonAssoc:
    """Неассоциативность с указанным приоритетом"""
    priority: int


@dataclasses.dataclass(frozen=True)
class Prio:
    """Только приоритет (для разрешения shift/reduce в пользу shift)"""
    priority: float


# ============== Символы грамматики ==============

class Symbol:
    """Базовый класс для всех символов грамматики"""
    pass


class BaseTerminal(Symbol):
    """Базовый класс для терминалов"""
    pass


class Terminal(BaseTerminal):
    """Терминал, определяемый регулярным выражением.

    Args:
        name: Имя терминала для отображения
        regex: Регулярное выражение для распознавания
        func: Функция преобразования совпавшего текста в атрибут
        priority: Приоритет при конфликтах лексера (больше = выше)
    """
    def __init__(self, name, regex, func, *, priority=5, re_flags=re.MULTILINE):
        self.name = name
        self.regex = regex
        self.func = func
        self.priority = priority
        self.re = re.compile(regex, re_flags)

    def __repr__(self):
        return f'Terminal({self.name!r},{self.regex!r},{self.func!r})'

    def __str__(self):
        return self.name

    def match(self, string, pos):
        m = self.re.match(string, pos)
        if m != None:
            begin, end = m.span()
            attrib = self.func(string[begin:end])
            return end - begin, attrib
        else:
            return 0, None


class LiteralTerminal(BaseTerminal):
    """Терминал-литерал (ключевое слово или оператор).

    Создаётся автоматически при использовании строк в правилах:
    E |= (E, '+', E, ...)  # '+' становится LiteralTerminal('+')
    """
    def __init__(self, image):
        self.image = image
        self.priority = 10

    def __hash__(self):
        return hash(self.image)

    def __eq__(self, other):
        return type(self) == type(other) and self.image == other.image

    def __repr__(self):
        return f'LiteralTerminal({self.image!r})'

    def __str__(self):
        return repr(self.image)

    def match(self, string, pos):
        if string.startswith(self.image, pos):
            return len(self.image), None
        else:
            return 0, None


class SpecTerminal(BaseTerminal):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'SpecTerminal({self.name})'

    def __str__(self):
        return self.name


EOF_SYMBOL = SpecTerminal('EOF')
FREE_SYMBOL = SpecTerminal('#')


class ErrorTerminal(BaseTerminal):
    priority = -1

    @staticmethod
    def match(string, pos):
        assert pos < len(string)
        return 1, ErrorTerminal


@dataclasses.dataclass(frozen = True)
class ExAction():
    """Расширенное семантическое действие с доступом к координатам.

    Функция callee получает (attrs, coords, res_coord):
    - attrs: список атрибутов дочерних узлов (None отфильтрованы)
    - coords: список координат (Fragment) дочерних узлов
    - res_coord: результирующая координата (Fragment)
    """
    callee : object

    @staticmethod
    def wrap_simple_action(simple_fold):
        def extended_action(attrs, coords, res_coord):
            return simple_fold(*attrs)

        return ExAction(extended_action)


class NonTerminal(Symbol):
    """Нетерминал грамматики.

    Правила добавляются оператором |=:
        E = NonTerminal('E')
        E |= (E, '+', E, lambda a, b: a + b)  # E -> E '+' E
        E |= NUM                              # E -> NUM
    """
    def __init__(self, name):
        self.name = name
        self.productions = []
        self.lambdas = []
        self.prec_assoc = []  # Приоритет и ассоциативность для каждого правила

    def __repr__(self):
        return 'NonTerminal(' + repr(self.name) + ')'

    def __str__(self):
        return self.name

    def stringify(self, pretty=True):
        title = '%s: ' % self.name

        if pretty:
            separator = '\n%s| ' % (' ' * len(self.name))
        else:
            separator = ''

        def strprod(prod):
            return ' '.join(str(sym) for sym in prod)

        rules = separator.join(strprod(prod) for prod in self.productions)
        return title + rules


    @staticmethod
    def __wrap_literals(symbol):
        if isinstance(symbol, str):
            return LiteralTerminal(symbol)
        else:
            assert isinstance(symbol, Symbol)
            return symbol

    @staticmethod
    def __extract_prec_assoc(symbols):
        """Извлекает маркеры приоритета/ассоциативности из списка символов"""
        prec_assoc = None
        filtered = []
        for sym in symbols:
            if isinstance(sym, (Left, Right, NonAssoc, Prio)):
                prec_assoc = sym
            else:
                filtered.append(sym)
        return filtered, prec_assoc

    def __ior__(self, other):
        """Оператор |= для добавления правил к нетерминалу.

        Форматы:
        - (sym1, sym2, ..., func)     - правило с семантическим действием
        - (sym1, sym2, ..., Left(n), func) - с приоритетом и ассоциативностью
        - (sym1, sym2, ...)           - правило с действием по умолчанию
        - symbol                      - правило из одного символа
        - lambda: value               - пустое правило (ε)
        """
        is_callable = lambda obj: hasattr(obj, '__call__')
        is_fold = lambda obj: is_callable(obj) or isinstance(obj, ExAction)

        if other == ():
            self |= lambda: None
        elif isinstance(other, tuple) and isinstance(other[-1], ExAction):
            *symbols, fold = other
            symbols, prec_assoc = self.__extract_prec_assoc(symbols)
            symbols = [self.__wrap_literals(sym) for sym in symbols]
            self.productions.append(symbols)
            self.lambdas.append(fold)
            self.prec_assoc.append(prec_assoc)
        elif isinstance(other, tuple) and is_callable(other[-1]):
            self |= other[:-1] + (ExAction.wrap_simple_action(other[-1]),)
        elif isinstance(other, tuple):
            self |= other + (self.__default_fold,)
        elif isinstance(other, Symbol) or is_fold(other):
            self |= (other,)
        elif isinstance(other, str):
            self |= (LiteralTerminal(other),)
        else:
            raise Exception('Bad rule')

        return self

    @staticmethod
    def __default_fold(*args):
        if len(args) == 1:
            return args[0]
        elif len(args) == 0:
            return None
        else:
            raise RuntimeError('__default_fold', args)

    def enum_rules(self):
        return zip(self.productions, self.lambdas, self.prec_assoc)


# ============== Позиции и координаты ==============

@dataclasses.dataclass(frozen = True)
class Position:
    """Позиция в исходном тексте (смещение, строка, колонка)"""
    offset : int = 0
    line : int = 1
    col : int = 1

    def shift(self, text : str):
        offset, line, col = dataclasses.astuple(self)

        for char in text:
            if char == '\n':
                line += 1
                col = 1
            else:
                col += 1

        return Position(offset + len(text), line, col)

    def __str__(self):
        return f'({self.line}, {self.col})'


@dataclasses.dataclass(frozen = True)
class Fragment:
    """Фрагмент текста от start до following (не включая)"""
    start : Position
    following : Position

    def __str__(self):
        return f'{self.start}-{self.following}'


@dataclasses.dataclass
class Token:
    type : BaseTerminal
    pos : Fragment
    attr : object

    def __str__(self):
        if self.attr is not None:
            return f'{self.type}({self.attr})'
        else:
            return str(self.type)


class LrZeroItemTableEntry:
    def __init__(self):
        self.propagates_to = set()
        self.lookaheads = set()

    def __repr__(self):
        pattern = '{ propagatesTo: %s, lookaheads: %s }'
        return pattern % (repr(self.propagates_to), repr(self.lookaheads))


# Действия в таблице разбора LALR(1)
Shift = collections.namedtuple('Shift', 'state')   # Перенос: перейти в состояние
Reduce = collections.namedtuple('Reduce', 'rule')  # Свёртка: применить правило
Accept = collections.namedtuple('Accept', '')      # Принять: разбор успешен


class NonAssocConflict:
    """Маркер: действие запрещено из-за NonAssoc"""
    def __init__(self, operator):
        self.operator = operator


class ParsingTable:
    """Таблица разбора LALR(1) с автоматическим разрешением конфликтов"""

    def __init__(self, gr):
        self.grammar = gr

        self.terminals = ()
        self.nonterms = ()
        self.__ccol = ()
        self.n_states = 0

        self.goto = ()
        self.action = ()

        self.__setup_from_grammar(self.grammar)

    def __get_rule_prec_assoc(self, prod_index):
        """Получает приоритет и ассоциативность для правила"""
        if prod_index < len(self.grammar.prec_assoc):
            return self.grammar.prec_assoc[prod_index]
        return None

    def __get_terminal_prec(self, terminal):
        """Получает приоритет терминала из правил, где он последний"""
        for prod_index, (nt, prod, fold, _) in enumerate(self.grammar.productions):
            if prod_index < len(self.grammar.prec_assoc):
                prec = self.grammar.prec_assoc[prod_index]
                if prec is not None:
                    # Проверяем, содержит ли правило этот терминал
                    for sym in prod:
                        if sym == terminal or (isinstance(sym, LiteralTerminal) and
                                               isinstance(terminal, LiteralTerminal) and
                                               sym.image == terminal.image):
                            return prec.priority
        return None

    def __resolve_conflict(self, state_id, terminal, actions):
        """Разрешает конфликт shift/reduce используя приоритет и ассоциативность"""
        if len(actions) <= 1:
            return actions

        shifts = [a for a in actions if isinstance(a, Shift)]
        reduces = [a for a in actions if isinstance(a, Reduce)]

        if len(shifts) == 1 and len(reduces) >= 1:
            shift_action = shifts[0]

            # Находим reduce с наибольшим приоритетом
            best_reduce = None
            best_reduce_prec = None

            for reduce_action in reduces:
                rule_prec = self.__get_rule_prec_assoc(reduce_action.rule)
                if rule_prec is not None:
                    if best_reduce_prec is None or rule_prec.priority > best_reduce_prec.priority:
                        best_reduce = reduce_action
                        best_reduce_prec = rule_prec

            if best_reduce_prec is not None:
                # Получаем приоритет терминала (символа, на который делается shift)
                shift_prec = self.__get_terminal_prec(terminal)

                if shift_prec is not None:
                    # Сравниваем приоритеты
                    if best_reduce_prec.priority > shift_prec:
                        # Приоритет reduce выше — выбираем reduce
                        return {best_reduce}
                    elif best_reduce_prec.priority < shift_prec:
                        # Приоритет shift выше — выбираем shift
                        return {shift_action}
                    else:
                        # Приоритеты равны — смотрим на ассоциативность
                        if isinstance(best_reduce_prec, Left):
                            return {best_reduce}
                        elif isinstance(best_reduce_prec, Right):
                            return {shift_action}
                        elif isinstance(best_reduce_prec, NonAssoc):
                            return NonAssocConflict(terminal)
                        elif isinstance(best_reduce_prec, Prio):
                            return {shift_action}  # По умолчанию shift
                else:
                    # Нет приоритета для терминала — используем только ассоциативность
                    if isinstance(best_reduce_prec, Left):
                        return {best_reduce}
                    elif isinstance(best_reduce_prec, Right):
                        return {shift_action}
                    elif isinstance(best_reduce_prec, NonAssoc):
                        return NonAssocConflict(terminal)
                    elif isinstance(best_reduce_prec, Prio):
                        return {shift_action}

        # Fallback: shift/reduce без приоритетов → предпочитаем shift (стандарт yacc/bison)
        if len(shifts) == 1 and len(reduces) >= 1:
            return {shifts[0]}

        # Fallback: reduce/reduce → предпочитаем более длинное правило (не ε),
        # при равной длине — правило с меньшим индексом
        if len(reduces) > 1 and len(shifts) == 0:
            best = max(reduces, key=lambda r: (
                len(self.grammar.productions[r.rule][1]),  # длина продукции
                -r.rule  # при равной длине — меньший индекс
            ))
            return {best}

        return actions

    def __setup_from_grammar(self, gr):
        self.terminals = gr.terminals + tuple([EOF_SYMBOL])
        self.nonterms = gr.nonterms[1:]

        self.__ccol = tuple(get_canonical_collection(gr))
        self.n_states = len(self.__ccol)

        ccol_core = tuple(drop_itemset_lookaheads(x) for x in self.__ccol)
        id_from_core = {ccol_core[i]: i for i in range(len(self.__ccol))}

        self.goto = tuple({x: None for x in self.nonterms} for i in range(self.n_states))
        self.action = tuple({x: set() for x in self.terminals} for i in range(self.n_states))

        goto_precalc = tuple(dict() for i in range(self.n_states))
        for symbol in (self.terminals + self.nonterms):
            for state_id in range(self.n_states):
                next_state = goto(gr, self.__ccol[state_id], symbol)
                if len(next_state) == 0:
                    continue
                next_state_id = id_from_core[drop_itemset_lookaheads(next_state)]
                goto_precalc[state_id][symbol] = next_state_id

        for state_id in range(self.n_states):
            for item, next_symbol in self.__ccol[state_id]:
                prod_index, dot = item
                pname, pbody, plambda, _ = gr.productions[prod_index]

                if dot < len(pbody):
                    terminal = pbody[dot]
                    if not isinstance(terminal, BaseTerminal) or terminal not in goto_precalc[state_id]:
                        continue

                    next_state_id = goto_precalc[state_id][terminal]
                    self.action[state_id][terminal].add(Shift(next_state_id))
                else:
                    if prod_index == 0:
                        assert (next_symbol == EOF_SYMBOL)
                        self.action[state_id][EOF_SYMBOL].add(Accept())
                    else:
                        self.action[state_id][next_symbol].add(Reduce(prod_index))

            for nt in self.nonterms:
                if nt not in goto_precalc[state_id]:
                    continue
                next_state_id = goto_precalc[state_id][nt]
                self.goto[state_id][nt] = next_state_id

        # Разрешаем конфликты с помощью приоритетов
        for state_id in range(self.n_states):
            for terminal in self.terminals:
                actions = self.action[state_id][terminal]
                if len(actions) > 1:
                    resolved = self.__resolve_conflict(state_id, terminal, actions)
                    self.action[state_id][terminal] = resolved

    @staticmethod
    def __stringify_action_entries(term, ent):
        return '\tfor terminal %s: ' % term + ', '.join(map(str, ent))

    @staticmethod
    def __stringify_goto_entry(nt, sid):
        return '\tfor non-terminal %s: go to state %d' % (str(nt), sid)

    def __stringify_lr_zero_item(self, item):
        prod_index, dot = item
        pname, pbody, plambda, _ = self.grammar.productions[prod_index]
        dotted_pbody = pbody[:dot] + ['.'] + pbody[dot:]
        dotted_pbody_str = ' '.join(str(x) for x in dotted_pbody)
        return RULE_INDEXING_PATTERN % (prod_index, pname.name + ': ' + dotted_pbody_str)

    def stringify_state(self, state_id):
        state_title = 'State %d\n' % state_id
        items = drop_itemset_lookaheads(kernels(self.__ccol[state_id]))
        items = sorted(items, key=lambda elem: elem[0])
        items_str = '\n'.join('\t' + self.__stringify_lr_zero_item(item) for item in items) + '\n\n'
        # TODO CHANGED FOR TERMINALS MAYBE WRONG
        actions = [(t, e) for t, e in self.action[state_id].items() if len(e) > 0]
        actions_str = '\n'.join(self.__stringify_action_entries(t, e) for t, e in actions)
        actions_str += ('\n' if len(actions_str) > 0 else '')

        gotos = [(nt, sid) for nt, sid in self.goto[state_id].items() if sid is not None]
        gotos = sorted(gotos, key=lambda elem: elem[0].name)

        gotos_str = '\n'.join(self.__stringify_goto_entry(nt, sid) for nt, sid in gotos)
        gotos_str += ('\n' if len(gotos_str) > 0 else '')

        action_goto_separator = ('\n' if len(actions_str) > 0 and len(gotos_str) > 0 else '')
        return state_title + items_str + actions_str + action_goto_separator + gotos_str

    def stringify(self):
        states_str = '\n'.join(self.stringify_state(i) for i in range(self.n_states))
        return states_str

    @staticmethod
    def __get_entry_status(e):
        if len(e) <= 1:
            return STATUS_OK
        n_actions = len(frozenset(type(a) for a in e))
        return STATUS_SR_CONFLICT if n_actions == 2 else STATUS_RR_CONFLICT

    def get_single_state_conflict_status(self, state_id):
        seq = [self.__get_entry_status(e) for t, e in self.action[state_id].items()]
        return STATUS_OK if len(seq) == 0 else max(seq)

    def get_conflict_status(self):
        return [self.get_single_state_conflict_status(i) for i in range(self.n_states)]

    def is_lalr_one(self):
        seq = self.get_conflict_status()
        return (STATUS_OK if len(seq) == 0 else max(seq)) == STATUS_OK


def get_canonical_collection(gr):
    dfa = LR0_Automaton(gr)
    kstates = dfa.kstates()
    n_states = len(kstates)

    table = [{item: LrZeroItemTableEntry() for item in kstates[i]} for i in range(n_states)]
    table[0][(0, 0)].lookaheads.add(EOF_SYMBOL)

    for i_state_id in range(n_states):
        state_symbols = [x[1] for x, y in dfa.goto.items() if x[0] == i_state_id]

        for i_item in kstates[i_state_id]:
            closure_set = closure(gr, [(i_item, FREE_SYMBOL)])

            for sym in state_symbols:
                j_state_id = dfa.goto[(i_state_id, sym)]

                # For each item in closure_set whose . (dot) points to a symbol equal to 'sym'
                # i.e. a production expecting to see 'sym' next
                for ((prod_index, dot), next_symbol) in closure_set:
                    pname, pbody, plambda, _ = gr.productions[prod_index]
                    if dot == len(pbody) or pbody[dot] != sym:
                        continue

                    j_item = (prod_index, dot + 1)
                    if next_symbol == FREE_SYMBOL:
                        table[i_state_id][i_item].propagates_to.add((j_state_id, j_item))
                    else:
                        table[j_state_id][j_item].lookaheads.add(next_symbol)

    repeat = True
    while repeat:
        repeat = False
        for i_state_id in range(len(table)):
            for i_item, i_cell in table[i_state_id].items():
                # For every kernel item i_item's lookaheads propagate to
                for j_state_id, j_item in i_cell.propagates_to:
                    j_cell = table[j_state_id][j_item]
                    j_cell_lookaheads_len = len(j_cell.lookaheads)
                    j_cell.lookaheads.update(i_cell.lookaheads)
                    if j_cell_lookaheads_len < len(j_cell.lookaheads):
                        repeat = True

    result = [set() for i in range(n_states)]
    for i_state_id in range(n_states):
        for i_item, i_cell in table[i_state_id].items():
            for sym in i_cell.lookaheads:
                item_set = (i_item, sym)
                result[i_state_id].add(item_set)
        result[i_state_id] = closure(gr, result[i_state_id])

    return result


def closure(gr, item_set):
    result = set(item_set)
    current = item_set

    while len(current) > 0:
        new_elements = []
        for ((prod_index, dot), lookahead) in current:
            pname, pbody, plambda, _ = gr.productions[prod_index]
            if dot == len(pbody) or pbody[dot] not in gr.nonterms:
                continue
            nt = pbody[dot]
            nt_offset = gr.nonterm_offset[nt]
            following_symbols = pbody[dot + 1:] + [lookahead]
            following_terminals = gr.first_set(following_symbols) - {None}
            for idx in range(len(nt.productions)):
                for term in following_terminals:
                    new_item_set = ((nt_offset + idx, 0), term)
                    if new_item_set not in result:
                        result.add(new_item_set)
                        new_elements += [new_item_set]
        current = new_elements
    return frozenset(result)


class Error(Exception, abc.ABC):
    @abc.abstractproperty
    def message(self):
        pass

    def __str__(self):
        return self.message


# ============== Пользовательские лексические ошибки ==============

class LexerUserError(Error):
    """Исключение для пользовательских лексических ошибок"""
    def __init__(self, message, pos=None):
        self.user_message = message
        self.pos = pos
        super().__init__(message)

    @property
    def message(self):
        if self.pos:
            return f'{self.pos}: {self.user_message}'
        return self.user_message


# Алиас для обратной совместимости
TokenAttributeError = LexerUserError


@dataclasses.dataclass
class ParseError(Error):
    pos : Position
    unexpected : Symbol
    expected : list

    @property
    def message(self):
        if isinstance(self.unexpected, Exception):
            # Если это LexerError, используем его message
            if hasattr(self.unexpected, 'message'):
                return self.unexpected.message
            return str(self.unexpected)
        expected = ', '.join(map(str, self.expected))
        if expected:
            return f'{self.pos}: Неожиданный символ {self.unexpected}, ' \
                    + f'ожидалось {expected}'
        return f'{self.pos}: Неожиданный символ {self.unexpected} на конце'


@dataclasses.dataclass
class NonAssocError(Error):
    """Ошибка: оператор с NonAssoc не допускает цепочки"""
    pos: Position
    operator: BaseTerminal

    @property
    def message(self):
        return f"{self.pos}: оператор {self.operator} не допускает цепочки (NonAssoc)"


@dataclasses.dataclass
class EarleyAmbiguityError(Error):
    """Ошибка: грамматика неоднозначна для данного входа"""
    pos: Position = dataclasses.field(default_factory=Position)

    @property
    def message(self):
        return f"{self.pos}: Неоднозначность грамматики: существует несколько деревьев разбора"


@dataclasses.dataclass
class LL1Error(Error):
    """Ошибка: грамматика не является LL(1)"""
    conflicts: list

    @property
    def message(self):
        return 'Грамматика не является LL(1): ' + '; '.join(self.conflicts)


# ============== LL(1) Таблица разбора ==============

class LL1Table:
    """Таблица предиктивного разбора LL(1).

    Строит таблицу M[A, a] по FIRST и FOLLOW множествам.
    Обнаруживает конфликты FIRST/FIRST и FIRST/FOLLOW.
    """
    def __init__(self, gr):
        self.grammar = gr
        self.terminals = gr.terminals + (EOF_SYMBOL,)
        self.nonterms = gr.nonterms[1:]  # Без фиктивной аксиомы
        self.table = {}  # table[(nonterminal, terminal)] -> (production_index, production)
        self.conflicts = []

        self.__build_table()

    def __build_table(self):
        gr = self.grammar

        for nt in self.nonterms:
            for terminal in self.terminals:
                self.table[(nt, terminal)] = None

        for prod_index, (nt, prod, fold, _) in enumerate(gr.productions):
            if prod_index == 0:  # Пропускаем фиктивную аксиому
                continue

            first_of_prod = gr.first_set(prod)

            for terminal in first_of_prod:
                if terminal is None:
                    continue
                if self.table.get((nt, terminal)) is not None:
                    existing = self.table[(nt, terminal)]
                    self.conflicts.append(
                        f'Конфликт FIRST/FIRST для {nt} на {terminal}: '
                        f'правила {existing[0]} и {prod_index}'
                    )
                else:
                    self.table[(nt, terminal)] = (prod_index, prod, fold)

            if None in first_of_prod:
                follow_nt = self.__compute_follow(nt)
                for terminal in follow_nt:
                    if self.table.get((nt, terminal)) is not None:
                        existing = self.table[(nt, terminal)]
                        self.conflicts.append(
                            f'Конфликт FIRST/FOLLOW для {nt} на {terminal}: '
                            f'правила {existing[0]} и {prod_index}'
                        )
                    else:
                        self.table[(nt, terminal)] = (prod_index, prod, fold)

    def __compute_follow(self, target_nt):
        """Вычисляет FOLLOW-множество для нетерминала"""
        gr = self.grammar
        follow = {nt: set() for nt in gr.nonterms}

        # FOLLOW стартового символа содержит EOF
        follow[gr.start_nonterminal].add(EOF_SYMBOL)

        changed = True
        while changed:
            changed = False
            for nt, prod, fold, _ in gr.productions:
                for i, sym in enumerate(prod):
                    if not isinstance(sym, NonTerminal):
                        continue

                    following = prod[i + 1:]
                    first_following = gr.first_set(following)

                    old_len = len(follow[sym])
                    follow[sym].update(first_following - {None})

                    if None in first_following or len(following) == 0:
                        follow[sym].update(follow[nt])

                    if len(follow[sym]) > old_len:
                        changed = True

        return follow.get(target_nt, set())

    def is_ll1(self):
        return len(self.conflicts) == 0


# ============== Алгоритм Эрли ==============

@dataclasses.dataclass
class EarleyItem:
    """Элемент Эрли: (правило, позиция точки, начальная позиция)"""
    prod_index: int
    dot: int
    origin: int
    # Для построения дерева разбора
    back_pointers: list = dataclasses.field(default_factory=list)

    def __hash__(self):
        return hash((self.prod_index, self.dot, self.origin))

    def __eq__(self, other):
        return (self.prod_index == other.prod_index and
                self.dot == other.dot and
                self.origin == other.origin)

    def __repr__(self):
        return f'EarleyItem({self.prod_index}, {self.dot}, {self.origin})'


class EarleyParser:
    """Парсер по алгоритму Эрли для произвольных КС-грамматик.

    Три основные операции:
    - Prediction: предсказание правил для нетерминала
    - Scanning: сопоставление терминала с токеном
    - Completion: завершение разбора правила
    """

    def __init__(self, grammar, ambiguity='warn'):
        self.grammar = grammar
        self.productions = grammar.productions
        self.start_symbol = grammar.start_nonterminal
        self.ambiguity = ambiguity

    def parse(self, tokens):
        """
        Разбор списка токенов по алгоритму Эрли.
        tokens: список Token
        Возвращает результат семантического действия.
        Поднимает ParseError при синтаксической ошибке,
        EarleyAmbiguityError или warnings.warn при неоднозначности.
        """
        n = len(tokens)
        self._ambiguity_detected = False

        # Создаём n+1 множеств состояний (используем dict для быстрого поиска)
        chart = [{} for _ in range(n + 1)]

        # Инициализация: добавляем начальные элементы
        for prod_index, (nt, prod, fold, _) in enumerate(self.productions):
            if prod_index == 0:  # Фиктивная аксиома $accept
                item = EarleyItem(prod_index, 0, 0)
                chart[0][self.__item_key(item)] = item

        # Обрабатываем каждое множество
        for i in range(n + 1):
            self.__process_chart(chart, i, tokens)

            # Проверяем опустошение: если не все токены обработаны,
            # но в следующем множестве нет элементов — неожиданный токен или лишний символ
            if i < n and len(chart[i + 1]) == 0:
                token = tokens[i]
                expected = self.__expected_terminals(chart[i])
                raise ParseError(
                    pos=token.pos.start,
                    unexpected=token,
                    expected=sorted(expected, key=str)
                )

        # Проверяем успешность разбора
        for key, item in chart[n].items():
            if item.prod_index == 0 and item.origin == 0:
                prod = self.productions[0]
                if item.dot == len(prod[1]):
                    # Проверяем неоднозначность
                    if self._ambiguity_detected:
                        if self.ambiguity == 'error':
                            pos = tokens[0].pos.start if n > 0 else Position()
                            raise EarleyAmbiguityError(pos=pos)
                        else:
                            warnings.warn(
                                "Неоднозначность грамматики: "
                                "существует несколько деревьев разбора",
                                stacklevel=2
                            )
                    # Разбор успешен, строим результат
                    return self.__build_parse_tree(chart, tokens, item, n)

        # Нет завершающего состояния — ошибка
        if n > 0:
            pos = tokens[-1].pos.following
        else:
            pos = Position()
        expected = self.__expected_terminals(chart[n])
        raise ParseError(
            pos=pos,
            unexpected=EOF_SYMBOL,
            expected=sorted(expected, key=str)
        )

    def __item_key(self, item):
        return (item.prod_index, item.dot, item.origin)

    def __expected_terminals(self, chart_set):
        """Собирает ожидаемые терминалы из множества состояний Эрли"""
        expected = set()
        for key, item in chart_set.items():
            prod_index = item.prod_index
            nt, prod, fold, _ = self.productions[prod_index]
            if item.dot < len(prod):
                next_sym = prod[item.dot]
                if isinstance(next_sym, BaseTerminal):
                    expected.add(next_sym)
        return list(expected)

    def __process_chart(self, chart, i, tokens):
        """Обрабатывает i-е множество состояний"""
        agenda = list(chart[i].values())
        idx = 0

        while idx < len(agenda):
            item = agenda[idx]
            idx += 1

            prod_index = item.prod_index
            nt, prod, fold, _ = self.productions[prod_index]
            dot = item.dot

            if dot < len(prod):
                next_sym = prod[dot]

                if isinstance(next_sym, NonTerminal):
                    # Prediction
                    for new_item in self.__predict(next_sym, i):
                        key = self.__item_key(new_item)
                        if key not in chart[i]:
                            chart[i][key] = new_item
                            agenda.append(new_item)

                elif isinstance(next_sym, BaseTerminal) and i < len(tokens):
                    # Scanning
                    token = tokens[i]
                    if self.__terminal_matches(next_sym, token):
                        new_item = EarleyItem(prod_index, dot + 1, item.origin)
                        new_item.back_pointers = item.back_pointers + [('scan', i, token)]
                        key = self.__item_key(new_item)
                        if key not in chart[i + 1]:
                            chart[i + 1][key] = new_item
                        else:
                            self._ambiguity_detected = True
            else:
                # Completion
                for new_item in self.__complete(chart, item, i):
                    key = self.__item_key(new_item)
                    if key not in chart[i]:
                        chart[i][key] = new_item
                        agenda.append(new_item)
                    else:
                        self._ambiguity_detected = True

    def __predict(self, nonterminal, position):
        """Prediction: добавляет элементы для всех правил нетерминала"""
        items = []
        for prod_index, (nt, prod, fold, _) in enumerate(self.productions):
            if nt == nonterminal:
                items.append(EarleyItem(prod_index, 0, position))
        return items

    def __complete(self, chart, completed_item, position):
        """Completion: продвигает элементы, ожидающие завершённый нетерминал"""
        items = []
        completed_nt, _, _, _ = self.productions[completed_item.prod_index]
        origin = completed_item.origin

        for key, item in chart[origin].items():
            prod_index = item.prod_index
            nt, prod, fold, _ = self.productions[prod_index]
            dot = item.dot

            if dot < len(prod) and prod[dot] == completed_nt:
                new_item = EarleyItem(prod_index, dot + 1, item.origin)
                new_item.back_pointers = item.back_pointers + [('complete', completed_item, position)]
                items.append(new_item)

        return items

    def __terminal_matches(self, terminal, token):
        """Проверяет, соответствует ли терминал токену"""
        if isinstance(terminal, LiteralTerminal):
            if isinstance(token.type, LiteralTerminal):
                return terminal.image == token.type.image
            return False
        return terminal == token.type

    def __build_parse_tree(self, chart, tokens, final_item, end_pos):
        """Строит результат разбора с вычислением семантических действий"""
        return self.__evaluate(chart, tokens, final_item, end_pos)

    def __evaluate(self, chart, tokens, item, end_pos):
        """Вычисляет семантическое действие для элемента Эрли"""
        prod_index = item.prod_index
        nt, prod, fold, _ = self.productions[prod_index]

        if len(prod) == 0:
            # Пустое правило
            pos = Position()
            res_coord = Fragment(pos, pos)
            return fold.callee([], [], res_coord)

        # Собираем атрибуты из back_pointers
        attrs = []
        coords = []

        for bp in item.back_pointers:
            if bp[0] == 'scan':
                # Терминал
                _, token_idx, token = bp
                attrs.append(token.attr)
                coords.append(token.pos)
            elif bp[0] == 'complete':
                # Нетерминал
                _, completed_item, pos = bp
                sub_result = self.__evaluate(chart, tokens, completed_item, pos)
                attrs.append(sub_result)
                # Вычисляем координаты для нетерминала
                if completed_item.origin < len(tokens):
                    start = tokens[completed_item.origin].pos.start
                else:
                    start = Position()
                if pos > 0 and pos <= len(tokens):
                    end = tokens[pos - 1].pos.following
                else:
                    end = start
                coords.append(Fragment(start, end))

        # Фильтруем None атрибуты (для совместимости с ExAction)
        filtered_attrs = [a for a in attrs if a is not None]

        # Вычисляем результирующую координату
        if len(coords) > 0:
            res_coord = Fragment(coords[0].start, coords[-1].following)
        else:
            pos = Position()
            res_coord = Fragment(pos, pos)

        return fold.callee(filtered_attrs, coords, res_coord)


class Parser(object):
    """Главный класс парсера.

    Пример использования:
        NUM = Terminal('NUM', r'\d+', int)
        E = NonTerminal('E')
        E |= (E, '+', E, lambda a, b: a + b)
        E |= NUM

        parser = Parser(E, method=LALR1)
        parser.add_skipped_domain(r'\s+')  # Пропуск пробелов
        result = parser.parse('1 + 2 + 3')  # -> 6
    """

    def __init__(self, start_nonterminal, *, method=None):
        """
        Создаёт парсер для заданной грамматики.

        Args:
            start_nonterminal: Стартовый нетерминал грамматики
            method: Метод разбора (LALR1, LL1, EARLEY). По умолчанию LALR1.
        """
        if method is None:
            method = LALR1

        self.method = method
        self.start_nonterminal = start_nonterminal

        fake_axiom = NonTerminal(START_SYMBOL)
        fake_axiom |= start_nonterminal

        self.nonterms = []
        self.terminals = set()
        self.symbols = ()
        self.productions = []
        self.prec_assoc = []  # Приоритеты и ассоциативности для правил
        self.nonterm_offset = {}
        self.__first_sets = {}

        def register(symbol):
            if isinstance(symbol, BaseTerminal):
                self.terminals.add(symbol)
            else:
                assert(isinstance(symbol, NonTerminal))
                if symbol not in self.nonterms:
                    self.nonterms.append(symbol)

            return symbol

        register(fake_axiom)

        scanned_count = 0
        while scanned_count < len(self.nonterms):
            last_unscanned = len(self.nonterms)

            for nt_idx in range(scanned_count, last_unscanned):
                nt = self.nonterms[nt_idx]
                self.nonterm_offset[nt] = len(self.productions)

                for prod, func, prec in nt.enum_rules():
                    for symbol in prod:
                        register(symbol)
                    self.productions.append((nt, prod, func, prec))
                    self.prec_assoc.append(prec)

            scanned_count = last_unscanned

        self.terminals = tuple(sorted(self.terminals, key=lambda t: str(t)))
        self.nonterms = tuple(sorted(self.nonterms, key=lambda nt: nt.name))
        self.symbols = self.nonterms + self.terminals
        self.skipped_domains = []

        self.__build_first_sets()

        # Инициализация таблицы/парсера в зависимости от метода
        self.table = None
        self.ll1_table = None
        self.earley_parser = None

        if isinstance(method, _LALR1):
            self.table = ParsingTable(self)
        elif isinstance(method, _LL1):
            self.ll1_table = LL1Table(self)
            if not self.ll1_table.is_ll1():
                raise LL1Error(conflicts=self.ll1_table.conflicts)
        elif isinstance(method, _EARLEY):
            self.earley_parser = EarleyParser(self, ambiguity=method.ambiguity)
        else:
            raise ValueError(f'Неизвестный метод разбора: {method}')

    def first_set(self, x):
        result = set()
        skippable_symbols = 0
        for sym in x:
            fs = self.__first_sets.get(sym, {sym})
            result.update(fs - {None})
            if None in fs:
                skippable_symbols += 1
            else:
                break
        if skippable_symbols == len(x):
            result.add(None)
        return frozenset(result)

    def __build_first_sets(self):
        for s in self.nonterms:
            self.__first_sets[s] = set()
            if [] in s.productions:
                self.__first_sets[s].add(None)

        repeat = True
        while repeat:
            repeat = False

            for nt, prod, func, _ in self.productions:
                curfs = self.__first_sets[nt]
                curfs_len = len(curfs)
                curfs.update(self.first_set(prod))

                if len(curfs) > curfs_len:
                    repeat = True

        self.__first_sets = {x: frozenset(y) for x, y in self.__first_sets.items()}

    def stringify(self, indexes=True):
        lines = '\n'.join(nt.stringify() for nt in self.nonterms)
        if indexes:
            lines = '\n'.join(RULE_INDEXING_PATTERN % (x, y)
                              for x, y in enumerate(lines.split('\n')))
        return lines

    def __str__(self):
        return self.stringify()

    def add_skipped_domain(self, regex):
        self.skipped_domains.append(regex)

    def parse(self, text):
        """Выполняет синтаксический анализ текста выбранным методом"""
        if isinstance(self.method, _LALR1):
            return self.__parse_lalr1(text)
        elif isinstance(self.method, _LL1):
            return self.__parse_ll1(text)
        elif isinstance(self.method, _EARLEY):
            return self.__parse_earley(text)
        else:
            raise ValueError(f'Неизвестный метод разбора: {self.method}')

    def __parse_lalr1(self, text):
        """LALR(1) разбор"""
        lexer = Lexer(self.terminals, text, self.skipped_domains)
        stack = [(0, Fragment(Position(), Position()), None)]
        try:
            cur = lexer.next_token()
        except LexerError as lex_err:
            raise ParseError(pos=lex_err.pos, unexpected=lex_err, expected=[]) from lex_err

        while True:
            cur_state, cur_coord, top_attr = stack[-1]
            actions = self.table.action[cur_state][cur.type]

            # Проверяем на NonAssoc конфликт
            if isinstance(actions, NonAssocConflict):
                raise NonAssocError(pos=cur.pos.start, operator=actions.operator)

            action = next(iter(actions), None)

            match action:
                case Shift(state):
                    stack.append((state, cur.pos, cur.attr))
                    try:
                        cur = lexer.next_token()
                    except LexerError as lex_err:
                        raise ParseError(pos=lex_err.pos, unexpected=lex_err, expected=[]) from lex_err
                case Reduce(rule):
                    nt, prod, fold, _ = self.productions[rule]
                    n = len(prod)
                    # Фильтруем None атрибуты (для совместимости с ExAction)
                    attrs = [attr for state, coord, attr in stack[len(stack)-n:]
                             if attr != None]
                    coords = [coord for state, coord, attr in stack[len(stack)-n:]]
                    if len(coords) > 0:
                        res_coord = Fragment(coords[0].start, coords[-1].following)
                    else:
                        res_coord = Fragment(cur.pos.start, cur.pos.start)
                    del stack[len(stack)-n:]
                    goto_state = self.table.goto[stack[-1][0]][nt]
                    res_attr = fold.callee(attrs, coords, res_coord)
                    stack.append((goto_state, res_coord, res_attr))
                case Accept():
                    assert(len(stack) == 2)
                    return top_attr
                case None:
                    expected = [symbol for symbol, actions
                                in self.table.action[cur_state].items()
                                if len(actions) > 0]
                    raise ParseError(pos=cur.pos.start, unexpected=cur,
                                     expected=expected)

    def __parse_ll1(self, text):
        """LL(1) разбор (нисходящий предиктивный анализ)"""
        lexer = Lexer(self.terminals, text, self.skipped_domains)

        # Стартовый нетерминал
        start_nt = self.start_nonterminal

        # Стек символов (нетерминалы и терминалы)
        stack = [EOF_SYMBOL, start_nt]

        # Стек семантических действий и данных
        # Каждый элемент: {'fold': func, 'children': [], 'coords': [], 'expected_count': n}
        semantic_stack = []
        root_result = {'children': [], 'coords': []}

        cur = lexer.next_token()

        while len(stack) > 0:
            top = stack.pop()

            if isinstance(top, BaseTerminal):
                # Терминал
                if top == EOF_SYMBOL:
                    if cur.type == EOF_SYMBOL:
                        break
                    else:
                        raise ParseError(pos=cur.pos.start, unexpected=cur,
                                         expected=[EOF_SYMBOL])

                if self.__terminal_matches_ll1(top, cur):
                    # Добавляем атрибут терминала в текущий семантический контекст
                    if semantic_stack:
                        ctx = semantic_stack[-1]
                        ctx['children'].append(cur.attr)
                        ctx['coords'].append(cur.pos)
                        ctx['collected'] += 1
                        self.__try_reduce_ll1(semantic_stack, root_result)
                    else:
                        root_result['children'].append(cur.attr)
                        root_result['coords'].append(cur.pos)
                    cur = lexer.next_token()
                else:
                    raise ParseError(pos=cur.pos.start, unexpected=cur,
                                     expected=[top])

            elif isinstance(top, NonTerminal):
                # Нетерминал - ищем правило
                entry = self.ll1_table.table.get((top, cur.type))

                if entry is None:
                    expected = [t for (nt, t), e in self.ll1_table.table.items()
                                if nt == top and e is not None]
                    raise ParseError(pos=cur.pos.start, unexpected=cur,
                                     expected=expected)

                prod_index, prod, fold = entry

                # Создаём контекст для семантического действия
                ctx = {
                    'fold': fold,
                    'children': [],
                    'coords': [],
                    'expected_count': len(prod),
                    'collected': 0,
                    'cur_pos': cur.pos
                }
                semantic_stack.append(ctx)

                # Если правило пустое, сразу выполняем свёртку
                if len(prod) == 0:
                    self.__try_reduce_ll1(semantic_stack, root_result)
                else:
                    # Добавляем символы в стек в обратном порядке
                    for sym in reversed(prod):
                        stack.append(sym)

        # Возвращаем финальный результат
        if root_result['children']:
            return root_result['children'][0]
        return None

    def __try_reduce_ll1(self, semantic_stack, root_result):
        """Пытается выполнить свёртку, если собраны все дочерние элементы"""
        while semantic_stack:
            ctx = semantic_stack[-1]
            if ctx['collected'] < ctx['expected_count']:
                break

            semantic_stack.pop()
            fold = ctx['fold']
            # Фильтруем None атрибуты (для совместимости с ExAction)
            children = [c for c in ctx['children'] if c is not None]
            coords = ctx['coords']

            if len(coords) > 0:
                res_coord = Fragment(coords[0].start, coords[-1].following)
            else:
                res_coord = Fragment(ctx['cur_pos'].start, ctx['cur_pos'].start)

            result = fold.callee(children, coords, res_coord)

            # Передаём результат родителю
            if semantic_stack:
                parent = semantic_stack[-1]
                parent['children'].append(result)
                if len(coords) > 0:
                    parent['coords'].append(res_coord)
                parent['collected'] += 1
            else:
                root_result['children'].append(result)
                if len(coords) > 0:
                    root_result['coords'].append(res_coord)

    def __terminal_matches_ll1(self, terminal, token):
        """Проверяет соответствие терминала токену для LL(1)"""
        if isinstance(terminal, LiteralTerminal):
            if isinstance(token.type, LiteralTerminal):
                return terminal.image == token.type.image
            return False
        return terminal == token.type

    def __parse_earley(self, text):
        """Разбор по алгоритму Эрли"""
        lexer = Lexer(self.terminals, text, self.skipped_domains)

        # Собираем все токены
        tokens = []
        while True:
            token = lexer.next_token()
            if token.type == EOF_SYMBOL:
                break
            tokens.append(token)

        return self.earley_parser.parse(tokens)

    def tokenize(self, text):
        lexer = Lexer(self.terminals, text, self.skipped_domains)

        while True:
            token = lexer.next_token()
            yield token
            if token.type == EOF_SYMBOL:
                break

    def is_lalr_one(self):
        if self.table is None:
            # Строим таблицу временно для проверки
            temp_table = ParsingTable(self)
            return temp_table.is_lalr_one()
        return self.table.is_lalr_one()

    def is_ll1(self):
        if self.ll1_table is None:
            temp_table = LL1Table(self)
            return temp_table.is_ll1()
        return self.ll1_table.is_ll1()

    def print_table(self, file=sys.stdout):
        if self.table is not None:
            print(self.table.stringify(), file=file)
        elif self.ll1_table is not None:
            print("LL(1) таблица:", file=file)
            for (nt, term), entry in self.ll1_table.table.items():
                if entry is not None:
                    print(f"  M[{nt}, {term}] = правило {entry[0]}", file=file)
        else:
            print("Алгоритм Эрли не использует таблицу разбора", file=file)


def goto(gr, item_set, inp):
    result_set = set()
    for (item, lookahead) in item_set:
        prod_id, dot = item
        pname, pbody, plambda, _ = gr.productions[prod_id]
        if dot == len(pbody) or pbody[dot] != inp:
            continue

        new_item = ((prod_id, dot + 1), lookahead)
        result_set.add(new_item)

    result_set = closure(gr, result_set)
    return result_set


def kernels(item_set):
    return frozenset((item, nextsym) for item, nextsym in item_set if item[1] > 0 or item[0] == 0)


def drop_itemset_lookaheads(itemset):
    return frozenset((x[0], x[1]) for x, y in itemset)


def describe_grammar(gr):
    return '\n'.join([
        'Grammar rules (%d in total):' % len(gr.productions),
        str(gr) + '\n',
        'Grammar non-terminals (%d in total):' % len(gr.nonterms),
        '\n'.join('\t' + str(s) for s in gr.nonterms) + '\n',
        'Grammar terminals (%d in total):' % len(gr.terminals),
        '\n'.join('\t' + str(s) for s in gr.terminals)
    ])


def describe_parsing_table(table):
    conflict_status = table.get_conflict_status()

    def conflict_status_str(state_id):
        has_sr_conflict = (conflict_status[state_id] == STATUS_SR_CONFLICT)
        status_str = ('shift-reduce' if has_sr_conflict else 'reduce-reduce')
        return 'State %d has a %s conflict' % (state_id, status_str)

    return ''.join([
        'PARSING TABLE SUMMARY\n',
        'Is the given grammar LALR(1)? %s\n' % ('Yes' if table.is_lalr_one() else 'No'),
        ''.join(conflict_status_str(sid) + '\n' for sid in range(table.n_states)
                if conflict_status[sid] != STATUS_OK) + '\n',
        table.stringify()
    ])


RULE_INDEXING_PATTERN = '%-5d%s'
START_SYMBOL = '$accept'

STATUS_OK = 0
STATUS_SR_CONFLICT = 1
STATUS_RR_CONFLICT = 2


class LR0_Automaton:
    def __init__(self, gr):
        self.states = []
        self.id_from_state = dict()
        self.goto = dict()

        self.states = [LR0_Automaton.__closure(gr, [(0, 0)])]
        next_id = 0

        self.id_from_state[self.states[-1]] = next_id
        next_id += 1

        seen = set(self.states)
        set_queue = self.states
        while len(set_queue) > 0:
            new_elements = []
            for item_set in set_queue:
                item_set_id = self.id_from_state[item_set]
                for symbol in gr.symbols:
                    next_item_set = LR0_Automaton.__goto(gr, item_set, symbol)
                    if len(next_item_set) == 0:
                        continue
                    if next_item_set not in seen:
                        new_elements += [next_item_set]
                        seen.add(next_item_set)
                        self.states += [next_item_set]
                        self.id_from_state[self.states[-1]] = next_id
                        next_id += 1
                    self.goto[(item_set_id, symbol)] = self.id_from_state[next_item_set]
            set_queue = new_elements

    @staticmethod
    def __closure(gr, item_set):
        result = set(item_set)
        set_queue = item_set
        while len(set_queue) > 0:
            new_elements = []
            for itemProdId, dot in set_queue:
                pname, pbody, plambda, _ = gr.productions[itemProdId]
                if dot == len(pbody) or pbody[dot] not in gr.nonterms:
                    continue
                nt = pbody[dot]
                nt_offset = gr.nonterm_offset[nt]
                for idx in range(len(nt.productions)):
                    new_item_set = (nt_offset + idx, 0)
                    if new_item_set not in result:
                        new_elements += [new_item_set]
                        result.add(new_item_set)
            set_queue = new_elements
        return frozenset(result)


    @staticmethod
    def __goto(gr, item_set, inp):
        result_set = set()
        for prod_index, dot in item_set:
            pname, pbody, plambda, _ = gr.productions[prod_index]
            if dot < len(pbody) and pbody[dot] == inp:
                result_set.add((prod_index, dot + 1))
        result_set = LR0_Automaton.__closure(gr, result_set)
        return result_set


    @staticmethod
    def __kernels(item_set):
        return frozenset((x, y) for x, y in item_set if y > 0 or x == 0)

    def kstates(self):
        return [LR0_Automaton.__kernels(st) for st in self.states]


class LexerError(Error):
    ERROR_SLICE = 10

    def __init__(self, pos, text):
        self.pos = pos
        self.bad = text[pos.offset:pos.offset + self.ERROR_SLICE]

    def __repr__(self):
        return f'LexerError({self.pos!r},{self.bad!r})'

    @property
    def message(self):
        return f'Не удалось разобрать {self.bad!r}'


class Lexer:
    """Лексический анализатор (токенизатор).

    Выбирает терминал с наибольшим совпадением, при равенстве — с большим приоритетом.
    """
    def __init__(self, domains, text, skip):
        self.domains = list(domains)
        self.text = text
        self.pos = Position()
        self.skip_token = object()
        self.domains += [Terminal('-skip-', regex, lambda _: self.skip_token)
                         for regex in skip]
        self.domains.append(ErrorTerminal())

    def next_token(self):
        while self.pos.offset < len(self.text):
            offset = self.pos.offset
            matches = []

            for d in self.domains:
                try:
                    length, attr = d.match(self.text, offset)
                    matches.append((d, d.priority, length, attr))
                except LexerUserError as e:
                    # Передаём позицию в пользовательскую ошибку
                    e.pos = self.pos
                    raise

            domain, priority, length, attr = \
                    max(matches, key=lambda t: (t[2], t[1]))

            assert length > 0

            if attr is ErrorTerminal:
                raise LexerError(self.pos, self.text)

            new_pos = self.pos.shift(self.text[offset:offset + length])
            frag = Fragment(self.pos, new_pos)
            self.pos = new_pos
            if attr != self.skip_token:
                token = Token(domain, frag, attr)
                return token

        return Token(EOF_SYMBOL, Fragment(self.pos, self.pos), None)
