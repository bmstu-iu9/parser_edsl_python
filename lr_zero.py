class Automaton:
    def __init__(self, gr):
        self.states = []
        self.id_from_state = dict()
        self.goto = dict()

        self.states = [Automaton.__closure(gr, [(0, 0)])]
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
                    next_item_set = Automaton.__goto(gr, item_set, symbol)
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
                pname, pbody, plambda = gr.productions[itemProdId]
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
            pname, pbody, plambda = gr.productions[prod_index]
            if dot < len(pbody) and pbody[dot] == inp:
                result_set.add((prod_index, dot + 1))
        result_set = Automaton.__closure(gr, result_set)
        return result_set


    @staticmethod
    def __kernels(item_set):
        return frozenset((x, y) for x, y in item_set if y > 0 or x == 0)

    def kstates(self):
        return [Automaton.__kernels(st) for st in self.states]
