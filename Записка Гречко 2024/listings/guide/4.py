parser = Parser(expr)
result = parser.parse("1+2+3")

result = parser.parse_earley("1+2+3")

result = parser.parse_ll1("1+2+3")
