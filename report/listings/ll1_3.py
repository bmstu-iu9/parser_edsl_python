def _add_rule(self, nt, terminal, prod, fold):
        if terminal not in self.table[nt]:
            self.table[nt][terminal] = (prod, fold)
        else:
            existing = self.table[nt][terminal]
            raise PredictiveTableConflictError(
                nonterm=nt,
                terminal=terminal,
                existing_rule=existing,
                new_rule=(prod, fold)
            )

    def stringify(self):
        lines = []
        for nt in self.grammar.nonterms:
            row = self.table[nt]
            lines.append(f'{nt}:')
            for term, (alpha, fold) in row.items():
                alpha_str = ' '.join(str(s) for s in alpha) if alpha \
                    else  'v'
                lines.append(f'   {term} -> {alpha_str}')
        return '\n'.join(lines)
