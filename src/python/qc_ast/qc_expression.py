# TODO: let's re-work the expression tree
# would be nice if coeff_expr and qc_expression had the same underlying
# structure (which they do not, at the moment)
#
# maybe use a dictionary structure indexed by variable?
#
# why did i switch to using an expression tree for the expression? because i
# wanted a quick way to emit the function "applyA". but if the expression tree
# is done as a dictionary, constant folding, etc. happens automagically....
#
# i also figured an expression tree would be "simpler", but constant folding
# makes it that much harder....
#
# it's also easy enough to store the "coefficient" for variable 'x' as a
# Python string '%(param_name)s + ...' and then eval it, except that it might
# be unsafe....
#
# naw, we'll create a coefficient class or something to add, multiply, etc.
# coefficients... then expressions are just dicts of coefficients
#
# this goes back to my old implementation....
#
# new implementation:
#
# (a*b + 1)*x + ... + ... + ... + ...
# store expressions as {'x': ParameterExpression(a*b + 1), '...': ...}
#
# the "ParameterExpression" uses the proper import to create the right kind of
# matrix during code generation
#
# what about slices, transposes, etc.? what about atoms?
#
# they can be classes / expressions too
#
# so we need a way to get the coefficients of an expression...

from qc_ast import RelOp
from qc_vexity import Convex, Concave, Affine, Nonconvex, isaffine, isconvex, isconcave, increasing, decreasing, nonmonotone
from qc_sign import Positive, Negative, Neither, ispositive, isnegative
from qc_shape import Scalar, Vector, Matrix, isvector, ismatrix, isscalar
from ast import Node

import qcml
import operator
import re

def isconstant(x):
    return isinstance(x, Constant)

def isadd(x):
    return isinstance(x, Add)

def ismul(x):
    return isinstance(x, Mul)

def isnegate(x):
    return isinstance(x, Negate)

def isparameter(x):
    return isinstance(x, Parameter)


class AbstractExpression(Node):
    """ AbstractExpression AST node.

        Abstract base class.
    """
    def __neg__(self): return negate_node(self)

    def __sub__(self,other): return constant_folding_add(self, -other)

    def __add__(self,other): return constant_folding_add(self,other)

    def __mul__(self,other): return distribute(self, other)

    def __eq__(self, other): return _compare(self, other, operator.__eq__, '==')

    def __le__(self, other): return _compare(self, other, operator.__le__, '<=')

    def __ge__(self, other): return _compare(other, self, operator.__le__, '<=')

class Constant(AbstractExpression):
    """ Constant AST node.

        Contains a floating point number. It is Affine; its sign depends on
        the sign of the float.
    """
    def __init__(self, value):
        self.value = value  # value is a float
        self.vexity = Affine()
        if float(value) >= 0.0: self.sign = Positive()
        else: self.sign = Negative()
        self.shape = Scalar()
        self.isknown = True # whether or not the expression is known at
                            # runtime, used to keep track of "param" * "var"

    def __str__(self): return str(self.value)

    def __repr__(self): return "Constant(%s)" % self.value

    def children(self): return []

    attr_names = ('value', 'vexity', 'sign')

class Parameter(AbstractExpression):
    """ Parameter AST node.

        Contains a representation of Parameters. It is Affine; its sign and
        shape are supplied from QCML.
    """
    def __init__(self, value, shape, sign):
        self.value = value  # value is a str
        self.vexity = Affine()
        self.sign = sign
        self.shape = shape
        self.isknown = True

    def __str__(self): return str(self.value)

    def __repr__(self): return "Parameter('%s',%s)" % (self.value, self.shape)

    def children(self): return []

    attr_names = ('value', 'vexity', 'sign','shape')

class Variable(AbstractExpression):
    """ Variable AST node.

        Contains a representation of Variables. It is Affine; its sign is
        Neither positive nor negative. Its shape is supplied from QCML.
    """
    def __init__(self, value, shape):
        self.value = value  # value is a str
        self.vexity = Affine()
        self.sign = Neither()
        self.shape = shape
        self.isknown = False

    def __str__(self): return str(self.value)

    def __repr__(self): return "Variable('%s',%s)" % (self.value, self.shape)

    def children(self): return []

    attr_names = ('value', 'vexity', 'sign', 'shape')

class ToVector(Variable):
    """ ToVector AST node. Subclass of Variable.

        Cast a Variable with generic Shape into a vector.

        Typically, the tree (whenever a Variable is used in an expression)
        looks like the following:

            Operations --- ToVector --- Slice --- Variable
    """

    def __init__(self, expr):
        if isvector(expr):
            super(ToVector, self).__init__(expr, expr.shape)
        else:
            raise TypeError("Cannot construct a vector node from %s" % repr(expr))

    def children(self):
        nodelist = []
        if self.value is not None: nodelist.append(("expr", self.value))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')

class ToMatrix(Parameter):
    """ ToMatrix AST node. Subclass of Parameter.

        Cast a Parameter with generic Shape into a matrix.

        Typically, the tree (whenever a Parameter is used in an expression)
        looks like the following:

            Operations --- ToMatrix --- Slice --- Parameter

        TODO: During rewrite stage, collapse all subclasses of Parameter into
        a single node with slice information and shape information.
    """

    def __init__(self, expr):
        if ismatrix(expr):
            super(ToMatrix, self).__init__(expr, expr.shape, expr.sign)
        else:
            raise TypeError("Cannot construct a matrix node from %s" % repr(expr))

    def children(self):
        nodelist = []
        if self.value is not None: nodelist.append(("expr", self.value))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')

""" AbstractExpression AST nodes

    What follows are nodes that are used to form expressions.
"""
class Add(AbstractExpression):
    def __init__(self, left, right):
        if isconstant(right):
            # put constants on the "left" of the AST
            self.right = left
            self.left = right
        else:
            self.left = left
            self.right = right

        self.sign = left.sign + right.sign
        self.vexity = left.vexity + right.vexity
        self.shape = left.shape + right.shape
        self.isknown = left.isknown & right.isknown

    def __str__(self): return "%s + %s" % (self.left, self.right)

    def children(self):
        nodelist = []
        if self.left is not None: nodelist.append(("left", self.left))
        if self.right is not None: nodelist.append(("right", self.right))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign','shape')

class Sum(AbstractExpression):
    def __init__(self, x):
        self.arg = x
        self.sign = x.sign
        self.vexity = x.vexity
        self.shape = Scalar()
        self.isknown = x.isknown

    def __str__(self): return "sum(%s)" % self.arg

    def children(self):
        nodelist = []
        if self.arg is not None: nodelist.append(("arg", self.arg))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign','shape')


class Mul(AbstractExpression):
    """ Assumes the lefthand side is a Constant or a Parameter.

        Effectively a unary operator.
    """
    def __init__(self, left, right):
        if isconstant(right):
            self.left = right
            self.right = left
        else:
            self.left = left
            self.right = right

        self.sign = self.left.sign * self.right.sign
        self.shape = self.left.shape * self.right.shape
        self.isknown = self.left.isknown & self.right.isknown
        if self.left.isknown:
            if isaffine(self.right):
                self.vexity = Affine()
            elif (isconvex(self.right) and ispositive(self.left)) or \
                 (isconcave(self.right) and isnegative(self.left)):
                self.vexity = Convex()
            elif (isconcave(self.right) and ispositive(self.left)) or \
                 (isconvex(self.right) and isnegative(self.left)):
                self.vexity = Concave()
            else:
                self.vexity = Nonconvex()
        else:
            # do i raise an error? do i complain about non-dcp compliance?
            self.vexity = Nonconvex()
            raise TypeError("Not DCP compliant multiply %s * %s (lefthand side should be known Constant or Parameter)" % (repr(left), repr(right)))

    # we omit parenthesis since multiply is distributed out
    def __str__(self): return "%s*%s" % (self.left, self.right)

    def children(self):
        nodelist = []
        if self.left is not None: nodelist.append(("left", self.left))
        if self.right is not None: nodelist.append(("right", self.right))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')

class Negate(AbstractExpression):
    def __init__(self, expr):
        self.expr = expr
        self.sign = -expr.sign
        self.vexity = -expr.vexity
        self.shape = expr.shape
        self.isknown = expr.isknown

    # we omit the parenthesis since negate is distributed out
    def __str__(self): return "-%s" % self.expr

    def children(self):
        nodelist = []
        if self.expr is not None: nodelist.append(("expr", self.expr))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')

class Transpose(Parameter):
    """ Can only be applied to parameters
    """
    def __init__(self, expr):
        super(Transpose, self).__init__(expr, expr.shape.transpose(), expr.sign)

    def __str__(self): return "%s'" % self.value

    def children(self):
        nodelist = []
        if self.value is not None: nodelist.append(("value", self.value))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')

class Slice(Parameter,Variable):
    """ Can only be applied to parameters or variables.

        At the moment, assumes that begin and end are of type int
    """
    def __init__(self, expr, begin, end, dim):
        assert (type(begin) is int), "Expected beginning index to be an integer"
        assert (type(end) is int), "Expected end index to be an integer"
        assert (begin < end), "Beginning slice should be less than end"

        super(Slice, self).__init__(expr, expr.slice(begin, end, dim), expr.sign)

        self.slice_dim = dim
        self.begin = begin
        self.end = end

    def __str__(self):
        if isscalar(self.value):
            return "%s" % self.value
        if isvector(self.value):
            return "%s(%s:%s)" % (self.value, self.begin, self.end)

        dims = self.value.shape.num_dimensions*[':']
        dims[self.slice_dim] = "%s:%s" % (self.begin, self.end)
        return "%s(%s)" % (self.value, ','.join(dims))

    def children(self):
        nodelist = []
        if self.value is not None: nodelist.append(("value", self.value))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')

class Atom(AbstractExpression):
    """ Atom AST node.

        Stores the name of the atom and its arguments
    """
    def __init__(self,name,arguments):
        self.name = name
        self.arglist = arguments
        self.isknown = False    # disallow taking functions of parameters
        # get the attributes of the atom
        try:
            self.sign, self.vexity, self.shape = qcml.atoms[self.name].attributes(*self.arglist)
        except TypeError as e:
            msg = re.sub(r'attributes\(\)', r'%s' % self.name, str(e))
            raise TypeError(msg)

    def __str__(self): return "%s(%s)" % (self.name, ','.join(map(str, self.arglist)))

    def children(self):
        nodelist = []
        if self.arglist is not None: nodelist.append(("arglist", self.arglist))
        return tuple(nodelist)

    attr_names = ('name', 'vexity', 'sign', 'shape')

class Norm(AbstractExpression):
    def __init__(self, args):
        self.arglist = args
        self.sign, self.vexity, self.shape = qcml.qc_atoms.norm(args)
        self.isknown = False

    def __str__(self): return "norm(%s)" % (', '.join(map(str,self.arglist)))

    def children(self):
        nodelist = []
        if self.arglist is not None: nodelist.append(("arglist", self.arglist))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign','shape')

class Abs(AbstractExpression):
    def __init__(self, x):
        self.arg = x
        self.sign, self.vexity, self.shape = qcml.qc_atoms.abs_(self.arg)
        self.isknown = False

    def __str__(self): return "abs(%s)" % self.arg

    def children(self):
        nodelist = []
        if self.arg is not None: nodelist.append(("arg", self.arg))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign','shape')

class Vstack(AbstractExpression):
    """ Vstack AST node.

        Forms the vertical concatenation: [x; y; z].
    """
    def __init__(self, args):
        self.arglist = args
        self.vexity = sum(map(lambda x: x.vexity, args))    # WRONG
        self.sign = sum(map(lambda x: x.sign, args))        # WRONG
        self.shape = Scalar() #stack(map(lambda x: x.shape, args))

    def __str__(self): return "[%s]" % ('; '.join(map(str, self.arglist)))

    def children(self):
        nodelist = []
        if self.arglist is not None: nodelist.append(("arglist", self.arglist))
        return tuple(nodelist)

    attr_names = ('vexity', 'sign', 'shape')


""" Utility functions for expressions.
"""
def negate_node(x):
    """ Negates an AST node"""

    def _negate(x):
        """ Ensures Negate(Negate(x)) is just x."""
        if isnegate(x): return x.expr
        else: return Negate(x)

    if isconstant(x): return Constant(-x.value)
    if isadd(x):
        if isconstant(x.left): return Add(Constant(-x.left.value), _negate(x.right))
        return Add(_negate(x.left), _negate(x.right))
    if ismul(x):
        if isconstant(x.left): return Mul(Constant(-x.left.value), x.right)
        return Mul(_negate(x.left), x.right)
    return _negate(x)

def constant_folding_add(lhs,rhs):
    if isconstant(lhs) and lhs.value == 0: return rhs
    if isconstant(rhs) and rhs.value == 0: return lhs
    return _constant_folding(lhs, rhs, Add, isadd, operator.add)

def constant_folding_mul(lhs,rhs):
    if isconstant(lhs) and lhs.value == 1: return rhs
    if isconstant(rhs) and rhs.value == 1: return lhs
    if isconstant(lhs) and lhs.value == 0: return Constant(0)
    if isconstant(rhs) and rhs.value == 0: return Constant(0)
    return _constant_folding(lhs, rhs, Mul, ismul, operator.mul)

def distribute(lhs, rhs):
    """ Distribute multiply a*(x + y) = a*x + a*y
    """
    if isadd(lhs):
        return constant_folding_add(
            distribute(lhs.left, rhs),
            distribute(lhs.right, rhs)
        )
    elif isadd(rhs):
        return constant_folding_add(
            distribute(lhs,rhs.left),
            distribute(lhs,rhs.right)
        )
    elif isnegate(rhs):
        return constant_folding_mul(negate_node(lhs), rhs.expr)
    else:
        return constant_folding_mul(lhs,rhs)

""" Constant folding...
    TODO: explain how this works...
"""
def _constant_folding(lhs,rhs,op,isop,do_op):
    """ Generic code for constant folding. Only for associative operators.

        op:
            Operation node (must be AST Node subclass)

        isop:
            Function to check if a Node is this op

        do_op:
            Execute the operator (e.g, for Add node, this is operator.add)
    """
    if isconstant(lhs) and isconstant(rhs):
        return Constant(do_op(lhs.value, rhs.value))

    left = lhs
    right = rhs
    if isconstant(lhs) and isop(rhs):
        # left is constant and right is the result of an add
        # by convention, we'll put constants on the left leaf
        if isconstant(rhs.left):
            right = rhs.right
            left = Constant(do_op(rhs.left.value,lhs.value))
    elif isconstant(rhs) and isop(lhs):
        # right is constant and left is the result of an add
        # by convention, we'll put constants on the left leaf
        if isconstant(lhs.left):
            right = lhs.right
            left = Constant(do_op(lhs.left.value,rhs.value))
    elif isop(lhs) and isop(rhs) and isconstant(lhs.left) and isconstant(rhs.left):
        # if adding two add nodes with constants on both sides
        left = Constant(do_op(lhs.left.value, rhs.left.value))
        right = op(lhs.right, rhs.right)
    elif isop(lhs) and isconstant(lhs.left):
        # if there are constants on the lhs, move up tree
        left = lhs.left
        right = op(lhs.right, rhs)
    elif isop(rhs) and isconstant(rhs.left):
        # if there are constants on the rhs, move up tree
        left = rhs.left
        right = op(lhs,rhs.right)

    return op(left, right)

""" Simplifying comparisons
"""
def _compare(x,y,op,op_str):
    if isconstant(x) and isconstant(y):
        if op(x.value, y.value): return None
        raise ValueError("Boolean constraint %s %s %s is trivially infeasible." %(x,op_str,y))
    else:
        return RelOp(op_str, x - y, Constant(0))