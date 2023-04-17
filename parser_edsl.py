import lr_zero as lr_zero
import types
import inspect

nonTerminals = []


SKIP = object()

class Terminal:
    def __init__(self, regex, func):
        self.regex = regex
        self.func = func

    def __len__(self):
        return 1

class NonTerminal:
    def __init__(self, name, productions=[]):
        self.name = name
        self.productions = [(x.split() if isinstance(x, str) else x) for x in productions]
        self.lambdas = []

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

    def __ior__(self, other):
        if isinstance(other, tuple) and isinstance(other[-1], types.FunctionType):
            self.productions.append(other[:-1])
            self.lambdas.append(other[-1])
        elif isinstance(other, NonTerminal) or isinstance(other, str):
            self.productions.append([other])
            self.lambdas.append(lambda s: s)
        elif isinstance(other, tuple):
            self.productions.append(other)
            self.lambdas.append(lambda s: s)
        elif isinstance(other, Terminal):
            self.productions.append([other])
            self.lambdas.append(lambda s: s)
        else:
            self.productions.append(other)
            self.lambdas.append(lambda s: s)
        return self


# Expr = NonTerminal('Expr', ["Expr + ExprTerm"])
# print(Expr.productions)

# TODO: transfer to lexer class if not used
class Token:
    def __init__(self, type, pos):
        self.type = type
        self.pos = pos

    def __str__(self):
        return 'Token %s at %s ' % (self.type, self.pos)


class AttrToken:
    def __init__(self, type, value, pos):
        self.type = type
        self.value = value
        self.pos = pos

    def __str__(self):
        return 'AttrToken %s (%s) at %s ' % (self.type, str(self.value), self.pos)
      

class LrZeroItemTableEntry:
    def __init__(self):
        self.propagates_to = set()
        self.lookaheads = set()

    def __repr__(self):
        pattern = '{ propagatesTo: %s, lookaheads: %s }'
        return pattern % (repr(self.propagates_to), repr(self.lookaheads))


class ParsingTable:
    def __init__(self, gr):
        self.grammar = gr

        self.terminals = ()  
        self.nonterms = ()  
        self.__ccol = ()
        self.n_states = 0  
        
        self.goto = ()
        self.action = ()

        self.__setup_from_grammar(self.grammar)

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
                pname, pbody, plambda = gr.productions[prod_index]

                if dot < len(pbody):
                    terminal = pbody[dot]
                    if not (isinstance(terminal, str) or isinstance(terminal, Terminal)) or terminal not in goto_precalc[state_id]:
                        continue

                    next_state_id = goto_precalc[state_id][terminal]
                    self.action[state_id][terminal].add(('shift and go to state', next_state_id))
                else:
                    if prod_index == 0:
                        assert (next_symbol == EOF_SYMBOL)
                        self.action[state_id][EOF_SYMBOL].add(('accept', ''))
                    else:
                        self.action[state_id][next_symbol].add(('reduce using rule', prod_index))

            for nt in self.nonterms:
                if nt not in goto_precalc[state_id]:
                    continue
                next_state_id = goto_precalc[state_id][nt]
                self.goto[state_id][nt] = next_state_id

    @staticmethod
    def __stringify_action_entries(term, ent):
        return '\tfor terminal %s: ' % term + \
               ', '.join('%s %s' % (kind, str(arg)) for kind, arg in ent)

    @staticmethod
    def __stringify_goto_entry(nt, sid):
        return '\tfor non-terminal %s: go to state %d' % (str(nt), sid)

    def __stringify_lr_zero_item(self, item):
        prod_index, dot = item
        pname, pbody, plambda = self.grammar.productions[prod_index]
        dotted_pbody = pbody[:dot] + ['.'] + pbody[dot:]
        dotted_pbody_str = ' '.join(str(x) for x in dotted_pbody)
        return RULE_INDEXING_PATTERN % (prod_index, pname + ': ' + dotted_pbody_str)

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
        n_actions = len(frozenset(x for x, y in e))
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
    dfa = lr_zero.get_automaton(gr)
    kstates = [lr_zero.kernels(st) for st in dfa.states]
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
                    pname, pbody, plambda = gr.productions[prod_index]
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
            pname, pbody, plambda = gr.productions[prod_index]
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


class EDSL_Parser(object):
    __attrs__ = ['co']

    def __init__(self, start_nonterminal=None):
        # Стартовый символ либо передается, либо берется из первого правила
        if start_nonterminal is None or start_nonterminal not in nonTerminals:
            start_nonterminal = nonTerminals[0]

            self.nonterms = tuple([NonTerminal(START_SYMBOL, [[start_nonterminal.name]])] +
                              sorted(nonTerminals, key=lambda elem: elem.name))

        # TODO: FIX THAT ACCEPT DOESNT HAVE LAMBDA
        self.nonterms[0].lambdas.append(lambda s: s[1:-1])

        self.terminals = ()
        self.symbols = ()
        self.productions = ()
        self.nonterm_offset = {}
        self.__first_sets = {}

        nonterminal_by_name = {nt.name: nt for nt in self.nonterms}
        for nt in self.nonterms:
            for prod in nt.productions:
                for idx in range(len(prod)):
                    symbol = prod[idx]
                    if isinstance(symbol, str):
                        if symbol in nonterminal_by_name:
                            prod[idx] = nonterminal_by_name[symbol]
                        else:
                            # если в продукции появляется символ не из списка нетерминалов
                            self.terminals += tuple([symbol])
                    elif isinstance(symbol, NonTerminal):
                        if symbol not in self.nonterms:
                            msg = 'Non-terminal %s is not in the grammar' % repr(symbol)
                            raise KeyError(msg)
                    elif isinstance(symbol, Terminal):
                        self.terminals += tuple([symbol])
                    else:
                        msg = "Unsupported type '%s' inside of production " % type(symbol).__name__
                        raise TypeError(msg)

        self.terminals = tuple(set(self.terminals))
        self.symbols = self.nonterms + self.terminals

        for nt in self.nonterms:
            self.nonterm_offset[nt] = len(self.productions)
            self.productions += tuple(
                (nt.name, list(prod), nt.lambdas[idx]) for (idx, prod) in enumerate(nt.productions))
        # for (idx, prod) in enumerate(self.productions):
        # print(idx, inspect.getsource(prod[2]))
        # if len(nt.lambdas) > 0:
        #     for (idx, prod) in enumerate(nt.productions):
        #         print(nt.name, prod, inspect.getsource(nt.lambdas[idx]))
        # print("NT ", nt.name)
        # for lamb in nt.lambdas:
        #     print(inspect.getsource(lamb))

        self.__build_first_sets()

    def first_set(self, x):
        result = set()

        if isinstance(x, str):
            result.add(x)
        elif isinstance(x, NonTerminal):
            result = self.__first_sets[x]
        else:
            skippable_symbols = 0
            for sym in x:
                fs = self.first_set(sym)
                result.update(fs - {None})
                if None in fs:
                    skippable_symbols += 1
                else:
                    break
            if skippable_symbols == len(x):
                result.add(None)
        return frozenset(result)

    def __build_first_sets(self):
        for s in self.symbols:
            if isinstance(s, str) or isinstance(s, Terminal):
                self.__first_sets[s] = {s}
            else:
                self.__first_sets[s] = set()
                if [] in s.productions:
                    self.__first_sets[s].add(None)

        repeat = True
        while repeat:
            repeat = False
            for nt in self.nonterms:
                curfs = self.__first_sets[nt]
                curfs_len = len(curfs)

                for prod in nt.productions:
                    skippable_symbols = 0
                    for sym in prod:
                        fs = self.__first_sets[sym]
                        curfs.update(fs - {None})
                        if None in fs:
                            skippable_symbols += 1
                        else:
                            break
                    if skippable_symbols == len(prod):
                        curfs.add(None)
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


def goto(gr, item_set, inp):
    result_set = set()
    for (item, lookahead) in item_set:
        prod_id, dot = item
        pname, pbody, plambda = gr.productions[prod_id]
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
EOF_SYMBOL = '$end'
FREE_SYMBOL = '$#'

STATUS_OK = 0
STATUS_SR_CONFLICT = 1
STATUS_RR_CONFLICT = 2
