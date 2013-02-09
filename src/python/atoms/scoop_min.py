from scoop.expression import Expression, \
    increasing, decreasing, nonmonotone, \
    ispositive, isnegative, \
    POSITIVE, NEGATIVE, UNKNOWN, \
    SCALAR, VECTOR, CONVEX, CONCAVE, AFFINE
from utils import create_varname
import operator

# to prevent name clash with builtin, named with trailing '_'
def min_(*args):    
    # infer vexity from signed monotonicities
    vexity = CONCAVE | reduce(operator.or_, map(increasing, args))
    
    # the output is named differently, but is also an expression
    # determine the shape of the output (scalar if vector input, vector if 
    # list input)
    if len(args) == 1:
        v = Expression(vexity, args[0].sign, SCALAR, create_varname(), None)        
    elif len(args) > 1:
        if any(isnegative(e) for e in args): sign = NEGATIVE
        if all(ispositive(e) for e in args): sign = POSITIVE
        else: sign = UNKNOWN
        shape = reduce(operator.add, map(lambda x: x.shape, args))
        
        v = Expression(vexity, sign, shape, create_varname(), None)
    else:
        raise Exception("'min' cannot be called with zero arguments.")

    # declare the expansion in "SCOOP"
    lhs = map(lambda x: x - v, args)
    lines = [ 
        "variable %s %s" % (v.name, str.lower(v.shape.shape_str)) 
    ] + map(lambda x: "%s >= 0" % x.name, lhs )
                
    return (lines, v)  
    
