expr = NonTerminal("expr")

expr |= (expr, '+', expr, Left(1), lambda x, y, z: x + z)
expr |= number
