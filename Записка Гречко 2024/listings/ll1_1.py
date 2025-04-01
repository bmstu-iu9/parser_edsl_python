class PredictiveTableConflictError(Error):
    def __init__(self, nonterm, terminal, existing_rule, new_rule):
        self.nonterm = nonterm
        self.terminal = terminal
        self.existing_rule = existing_rule
        self.new_rule = new_rule

    @property
    def message(self):
        return (f'LL(1) conflict: {self.nonterm}  {self.terminal}\n'
                f'{self.existing_rule}, {self.new_rule}')


@dataclasses.dataclass
class ParseTreeNode:
    symbol: Symbol
    fold: ExAction = None
    token: Token = None
    children: list = dataclasses.field(default_factory=list)
    attribute: object = None
