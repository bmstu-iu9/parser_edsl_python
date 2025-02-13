def parse(self, tokens):
        start_rule = (self.grammar.nonterms[0],
            tuple(self.grammar.productions[0][1]), self.grammar.productions[0][2])
        self.chart[0].add(EarleyState(start_rule, 0, 0, 0))
        for pos in range(len(tokens)+1):
            states = list(self.chart[pos])
            for state in states:
                if not state.is_complete():
                    next_sym = state.next_symbol()
                    if isinstance(next_sym, NonTerminal):
                        self.predict(state, pos, states)
                    elif pos < len(tokens):
                        self.scan(state, tokens[pos], pos)
                else:
                    self.complete(state, pos, states)
            if len(states) == len(list(self.chart[pos])):
                print(tokens[pos])
                print(list(self.chart[pos-1])[0])
                raise ParseError(tokens[pos].pos.start,
                    unexpected=tokens[pos], expected=["+"])
            self.chart[pos].update(states)
        final_states = [state for state in self.chart[len(tokens)]
            if state.rule[0] == self.grammar.nonterms[1] and
                state.is_complete() and state.start == 0]

        if len(final_states) > 1:
            raise RuntimeError(f"Неопределенная грамматика: найдено
                {len(final_states)} путей разбора")
        if final_states:
            return final_states[0].attrs[0]
        return None

    def print_chart(self):
        """Print the Earley chart for debugging."""
        for pos, states in sorted(self.chart.items()):
            print(f"Chart[{pos}]:")
            for state in states:
                print(f"  {state}")
