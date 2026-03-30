@dataclasses.dataclass
class ParseError(Error):
    pos : Position
    unexpected : Symbol
    expected : list

class LexerError(Error):
    ERROR_SLICE = 10

    def __init__(self, pos, text):
        self.pos = pos
        self.bad = text[pos.offset:pos.offset + self.ERROR_SLICE]
