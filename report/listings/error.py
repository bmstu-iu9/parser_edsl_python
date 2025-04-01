def pos_from_offset(text, offset):
    line = text.count('\n', 0, offset) + 1
    last_newline = text.rfind('\n', 0, offset)
    col = offset - last_newline if last_newline != -1 else offset + 1
    return Position(offset, line, col)

class TokenAttributeError(Error):
    def __init__(self, text):
        self.bad = text
    def __repr__(self):
        return f'TokenAttributeError({self.pos!r},{self.bad!r})'
    @property
    def message(self):
        return f'{self.bad}'

class Terminal(BaseTerminal):
    ...
    def match(self, string, pos):
        ...
        try:
                attrib = self.func(string[begin:end])
            except TokenAttributeError as exc:
                raise LexerError(pos_from_offset(string, begin), string,
                        message=exc.message) from exc

...

class ParseError(Error):
     def parse(self, text):
          ...
          try:
            cur = lexer.next_token()
        except LexerError as lex_err:
            raise ParseError(pos=lex_err.pos, unexpected=lex_err,
                    expected=[], _text=lex_err.message) from lex_err
