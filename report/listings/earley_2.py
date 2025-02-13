class EarleyParser:
    """Implements the Earley parsing algorithm."""
    def __init__(self, grammar: Parser):
        self.grammar = grammar
        self.chart = defaultdict(set)

    def predict(self, state, pos, states):
        """Predictor step: Add new states for non-terminals."""
        next_sym = state.next_symbol()
        if isinstance(next_sym, NonTerminal):
            for prod, fold in next_sym.enum_rules():
                new_state = EarleyState((next_sym, tuple(prod), fold),
                     0, pos, pos)
                if new_state not in self.chart[pos] and new_state not in states:
                    states.append(new_state)
                    self.predict(new_state, pos, states)

    def scan(self, state, token, pos):
        """Scanner step: Match terminals with the input."""
        next_sym = state.next_symbol()
        if (isinstance(next_sym, LiteralTerminal) or
                isinstance(next_sym, Terminal)) and next_sym == token.type:
            new_attrs = state.attrs + (token.attr,)
            new_coords = state.coords + (token.pos,)
            new_state = EarleyState(state.rule, state.dot + 1,
                state.start, pos + 1, new_attrs, new_coords)
            self.chart[pos + 1].add(new_state)

    def complete(self, state, pos, states: list[EarleyState]):
        """Completer step: Propagate completed states."""
        for prev_state in self.chart[state.start]:
            next_sym = prev_state.next_symbol()
            if next_sym == state.rule[0]:
                state_attrs = state.attrs
                new_attrs = prev_state.attrs + state_attrs
                new_coords = prev_state.coords + state.coords
                new_state = EarleyState(
                    prev_state.rule,
                    prev_state.dot + 1,
                    prev_state.start,
                    pos,
                    new_attrs,
                    new_coords
                )
                if new_state not in self.chart[pos]:
                    states.append(new_state)
                    if not new_state.is_complete():
                        self.predict(new_state, pos, states)