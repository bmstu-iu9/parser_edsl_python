@dataclasses.dataclass(frozen=True)
class Precedence:
    level: int
    associativity: str
    def __repr__(self):
        return f"Precedence({self.associativity!r}, {self.level!r})"
@dataclasses.dataclass(frozen=True)
class Left(Precedence):
    level: int
    associativity: str = 'left'
@dataclasses.dataclass(frozen=True)
class Right(Precedence):
    level: int
    associativity: str = 'right'
@dataclasses.dataclass(frozen=True)
class NonAssoc(Precedence):
    level: int
    associativity: str = 'nonassoc'

if shift_action is not None and reduce_action is not None:
    _, _, fold, prod_prec = self.productions[reduce_action.rule]
    if prod_prec is None:
        prod = self.productions[reduce_action.rule][1]
        for sym in reversed(prod):
            if isinstance(sym, BaseTerminal):
                prod_prec = Precedence(sym.priority, 'left')
                break
    token_prec = cur.type.priority
    if prod_prec is None:
        action = shift_action
    elif token_prec > prod_prec.level:
        action = shift_action
    elif token_prec < prod_prec.level:
        action = reduce_action
    else:
        if prod_prec.associativity == 'left':
            action = reduce_action
        elif prod_prec.associativity == 'right':
            action = shift_action
        else:
            raise ParseError(pos=cur.pos.start, unexpected=cur,
                             expected=[cur.type])
