from .. node import Node
from ... errors import QC_DCPError
from ... properties import shape, curvature

class ProgramObjective(object):
    """ ProgramObjective object.

        This object contains the representation of the objective. It also
        stores the objective's sense (minimize, maximize, or find).

        It is DCP compliant when the objective's expression agrees with its
        sense. Convex for minimization, concave for maximization, or affine
        for find / feasibility problems.

        It is *not* an expression node; it lives inside an SOCP and is
        canonicalized separately.
    """
    check_dcp = {
        'minimize': curvature.isconvex,
        'maximize': curvature.isconcave,
        'find': curvature.isaffine
    }

    def __init__(self, sense, expr):
        # for debugging, ensure that objectives are canonicalizable and showable
        assert(isinstance(expr, Node))
        if not shape.isscalar(expr):
            raise QC_DCPError("Objective is not scalar")

        self.sense = sense
        self.expr = expr
        try:
            self.is_dcp = ProgramObjective.check_dcp[sense](expr)
        except KeyError:
            raise Exception("Unrecognized problem sense '%s'" % sense)

    def __str__(self):
        return "%s %s" % (self.sense, self.expr)

