class PredictiveParsingTable:
    def __init__(self, grammar):
        self.grammar = grammar
        self.table = {}

        self.follow_sets = self._build_follow_sets()
        self._build_table()

    def _build_follow_sets(self):
        follow = {nt: set() for nt in self.grammar.nonterms}
        start_nt = self.grammar.nonterms[0]

        follow[start_nt].add(EOF_SYMBOL)

        changed = True
        while changed:
            changed = False
            for (nt, prod, _, _) in self.grammar.productions:
                for i, sym in enumerate(prod):
                    if sym not in self.grammar.nonterms:
                        continue
                    beta = prod[i+1:]
                    first_of_beta = self.grammar.first_set(beta)
                    before_len = len(follow[sym])

                    without_epsilon = set(first_of_beta) - {None}
                    follow[sym].update(without_epsilon)

                    if None in first_of_beta:
                        follow[sym].update(follow[nt])

                    after_len = len(follow[sym])
                    if after_len > before_len:
                        changed = True
        return follow

    def _build_table(self):
        for nt in self.grammar.nonterms:
            self.table[nt] = {}

        for i, (nt, prod, fold, _) in enumerate(self.grammar.productions):
            fs = self.grammar.first_set(prod)
            non_epsilon = fs - {None}
            for t in non_epsilon:
                self._add_rule(nt, t, prod, fold)

            if None in fs:
                for t in self.follow_sets[nt]:
                    self._add_rule(nt, t, prod, fold)
