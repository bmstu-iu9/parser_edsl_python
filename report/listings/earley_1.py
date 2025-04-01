@dataclasses.dataclass(frozen=True)
class EarleyState:
    rule: tuple
    dot: int
    start: int
    end: int
    attrs: tuple = ()
    coords: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, 'attrs', tuple(self.attrs))
        object.__setattr__(self, 'coords', tuple(self.coords))

    def __repr__(self):
        lhs, rhs, _ = self.rule
        dotted_rhs = ' '.join(str(x) for x in rhs[:self.dot]) + \
            ' • ' + ' '.join(str(x) for x in rhs[self.dot:])
        return f"{lhs} → {dotted_rhs} [{self.start}, {self.end}] \
            {self.is_complete()} attr({self.attrs})"

    def is_complete(self):
        _, rhs, _ = self.rule
        return self.dot == len(rhs)

    def next_symbol(self):
        _, rhs, _ = self.rule
        if self.dot < len(rhs):
            return rhs[self.dot]
        return None