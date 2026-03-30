import abc
import enum
import pytest
import parser_edsl as pe
import re
import typing

from dataclasses import dataclass

good_text = """var
  (* переменные *)
  x: integer;
begin
  { операторы }
  x := 100;
end
"""

bad_text = """
var
  (* переменные *)
  x: integer;
  y: integer;
begin
  { операторы }
  x := 100;
end
"""

class Type(enum.Enum):
    Integer = 'INTEGER'
    Real = 'REAL'
    Boolean = 'BOOLEAN'


@dataclass
class VarDef:
    name : str
    type : Type


class Statement(abc.ABC):
    pass


@dataclass
class Program:
    var_defs : list[VarDef]
    statements : list[Statement]


class Expr(abc.ABC):
    pass


@dataclass
class AssignStatement(Statement):
    variable : str
    expr : Expr


@dataclass
class VariableExpr(Expr):
    varname : str


@dataclass
class ConstExpr(Expr):
    value : typing.Any
    type : Type


@dataclass
class BinOpExpr(Expr):
    left : Expr
    op : str
    right : Expr


@dataclass
class UnOpExpr(Expr):
    op : str
    expr : Expr


def validate(str):
    if str == "a":
        raise pe.TokenAttributeError("pos", "dsadsa")
    return str.upper()

INTEGER = pe.Terminal('INTEGER', '[0-9]+', int, priority=7)
REAL = pe.Terminal('REAL', '[0-9]+(\\.[0-9]*)?(e[-+]?[0-9]+)?', float)
VARNAME = pe.Terminal('VARNAME', '[A-Za-z][A-Za-z0-9]*', validate)

def make_keyword(image):
    return pe.Terminal(image, image, lambda name: None,
                       re_flags=re.IGNORECASE, priority=10)

KW_VAR, KW_BEGIN, KW_END, KW_INTEGER, KW_REAL, KW_BOOLEAN = \
    map(make_keyword, 'var begin end integer real boolean'.split())

KW_IF, KW_THEN, KW_ELSE, KW_WHILE, KW_DO, KW_FOR, KW_TO = \
    map(make_keyword, 'if then else while do for to'.split())

KW_OR, KW_DIV, KW_MOD, KW_AND, KW_NOT, KW_TRUE, KW_FALSE = \
    map(make_keyword, 'or div mod and not true false'.split())


NProgram, NVarDefs, NVarDef, NType, NStatements = \
    map(pe.NonTerminal, 'Program VarDefs VarDef Type Statements'.split())

NStatement, NExpr, NCmpOp, NArithmExpr, NAddOp = \
    map(pe.NonTerminal, 'Statement Expr CmpOp ArithmOp AddOp'.split())

NTerm, NMulOp, NFactor, NPower, NConst = \
    map(pe.NonTerminal, 'Term MulOp Factor Power Const'.split())


NProgram |= KW_VAR, NVarDefs, KW_BEGIN, NStatements, KW_END, Program

NVarDefs |= lambda: []
NVarDefs |= NVarDef, lambda vd: [vd]

NVarDef |= VARNAME, ':', NType, ';', VarDef

NType |= KW_INTEGER, lambda: Type.Integer
NType |= KW_REAL, lambda: Type.Real
NType |= KW_BOOLEAN, lambda: Type.Boolean

NStatements |= NStatement, ';', lambda st: [st]

NStatement |= VARNAME, ':=', NExpr, AssignStatement

NExpr |= NArithmExpr

def make_op_lambda(op):
    return lambda: op

for op in ('>', '<', '>=', '<=', '=', '<>'):
    NCmpOp |= op, make_op_lambda(op)

NArithmExpr |= NTerm

NAddOp |= '+', lambda: '+'
NAddOp |= '-', lambda: '-'
NAddOp |= KW_OR, lambda: 'or'

NTerm |= NFactor

NMulOp |= '*', lambda: '*'
NMulOp |= '/', lambda: '/'
NMulOp |= KW_DIV, lambda: 'div'
NMulOp |= KW_MOD, lambda: 'mod'
NMulOp |= KW_AND, lambda: 'and'

NFactor |= NPower

NPower |= NConst

NConst |= INTEGER, lambda v: ConstExpr(v, Type.Integer)
NConst |= REAL, lambda v: ConstExpr(v, Type.Real)
NConst |= KW_TRUE, lambda: ConstExpr(True, Type.Boolean)
NConst |= KW_FALSE, lambda: ConstExpr(False, Type.Boolean)

def test_good_parse():
    p = pe.Parser(NProgram)
    p.add_skipped_domain('\\s')
    p.add_skipped_domain('(\\(\\*|\\{).*?(\\*\\)|\\})')
    assert p.parse_earley(good_text) == Program(var_defs=[VarDef(name='X', type=Type.Integer)], statements=[AssignStatement(variable='X', expr=ConstExpr(value=100, type=Type.Integer))])

def test_bad_parse():
    p = pe.Parser(NProgram)
    p.add_skipped_domain('\\s')
    p.add_skipped_domain('(\\(\\*|\\{).*?(\\*\\)|\\})')
    assert p.is_ll1()

    with pytest.raises(pe.ParseError) as parse_error:
        p.parse_earley(bad_text)

    assert parse_error.value.message == "Неожиданный символ VARNAME(Y), ожидалось begin"
