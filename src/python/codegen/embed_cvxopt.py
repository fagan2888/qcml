"""
Copyright (c) 2012-2013, Eric Chu (eytchu@gmail.com)
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met: 

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer. 
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are
those of the authors and should not be interpreted as representing official
policies, either expressed or implied, of the FreeBSD Project.
"""

import cvxopt as o
from cvxopt import solvers
from scoop.expression import Parameter
from codegen import mangle, ismultiply, height_of
# for embedded in python


# these functions should probably go into codegen
def eye(v,m):
    return o.spmatrix(v, range(m), range(m))

def ones(v,m):
    return o.spmatrix(v, range(m), [0]*m)
    
def onesT(v,m):
    return o.spmatrix(v, [0]*m, range(m))
    
# define how to evaluate a coefficient in a matrix
# a failure case sum(a*x), where x is scalar, but a is vector
# another failure case is A*B*C, where B has diff dimensions than C.cols
def eval_matrix_coeff(coeff, params, rows, cols):
    params['ones^T'] = onesT(1,cols)
    v = coeff.constant_value()
    if v:
        if cols == rows:
            return eye(v, rows)
        elif cols == 1:
            return ones(v, rows)
        else:
            raise Exception("Unknown matrix coeff...")
    else:
        value = 0
        for k,v in coeff.coeff_dict.iteritems():
            if k == '1':
                if cols == rows:
                    value += eye(v, rows)
                elif cols == 1:
                    value += ones(v, rows)
                else:
                    raise Exception("Unknown matrix coeff...")
            elif not ismultiply(k):
                value += v*params[k]
            else:
                keys = k.split('*')
                keys.reverse()
                mult = 1
                prev_param = None
                for k1 in keys:
                    
                    # in the special case where we we have something like
                    # sum(a*x) = 1^T*a*x and 'a' is a vector while x is scalar
                    # so the initial size of ones^T was not correct. we resize
                    # ones^T so that it "matches"
                    if k1 == 'ones^T':
                        params[k1] = onesT(1,prev_param.size[0])

                    #print params[k1]
                    mult = params[k1]*mult
                    prev_param = params[k1]
                value += v*mult
        return value.T

# define how to evaluate a coefficient in a vector
def eval_coeff(coeff, params, rows):
    v = coeff.constant_value()
    if v:
        return o.matrix(v, (rows,1))
    else:
        value = 0
        for k,v in coeff.coeff_dict.iteritems():
            if k == '1':
                value += o.matrix(v, (rows,1))
            elif not ismultiply(k):
                value += v*params[k]
            else:
                keys = k.split('*').reverse()
                mult = 1
                for k1 in keys:
                    mult *= params[k1]
                value += v*mult
        return value
        
def build_matrix(A,b,b_height, params,vec_sizes,start_idxs,total_width):
    h_cum = height_of(b_height, vec_sizes)
    h_vec = o.matrix(0, (h_cum,1), 'd')
    G_vals = []
    G_I, G_J = [], []
    idx = 0  
                     
    for row, coeff, size in zip(A,b,b_height):
        row_height = size.row_value(vec_sizes)
        h_vec[idx:idx+row_height] = eval_coeff(coeff, params, row_height)
        for k,v in row.iteritems():   # repeated function
            # we ignore constant coefficients
            if k != '1':
                col_width = vec_sizes[k]
                result_mat = o.sparse(eval_matrix_coeff(v, params, row_height, col_width))
                # set the row
                G_I += (result_mat.I + idx)
                # set the column
                G_J += (result_mat.J + start_idxs[k])
                # set the values
                G_vals += result_mat.V
                            
        idx += row_height

    Gl_mat = o.spmatrix(G_vals, G_I, G_J, (h_cum, total_width))
    hl_vec = h_vec
    return (Gl_mat, hl_vec)

def build_block_matrices(A_blk,b_blk,b_blk_height, params,vec_sizes,start_idxs,total_width):
    heights = map(lambda e:e.row_value(vec_sizes), b_blk_height)
    if any(e != heights[0] for e in heights):
        raise Exception("Expected blocks to be the same size!")
        
    blk_sz = len(A_blk)
    blk_height = heights[0]
    total_height = sum(heights)
    
    G_vals = []
    G_I, G_J = [], []
    idx = 0  
    h_vec = o.matrix(0, (total_height,1), 'd')
    
    for row, coeff, size in zip(A_blk,b_blk,b_blk_height):
        row_height = size.row_value(vec_sizes) # == blk_height
        h_vec[idx::blk_sz] = eval_coeff(coeff, params, row_height)
        for k,v in row.iteritems():   # repeated function
            # we ignore constant coefficients
            if k != '1':
                col_width = vec_sizes[k]
                result_mat = o.sparse(eval_matrix_coeff(v, params, row_height, col_width))
                # set the row
                G_I += (blk_sz*result_mat.I + idx)
                # set the column
                G_J += (result_mat.J + start_idxs[k])
                # set the values
                G_vals += result_mat.V
                            
        idx += row_height+1
        idx %= blk_height
    
    Gl_mat = o.spmatrix(G_vals, G_I, G_J, (total_height, total_width))
    hl_vec = h_vec
    
    # now, chop them up into 'blk_height' matrices, each with 'blk_sz' rows
    G_mats = []
    h_vecs = []
    for i in range(blk_height):
        G_mats.append(Gl_mat[blk_sz*i:blk_sz*i+blk_sz, :])
        h_vecs.append(hl_vec[blk_sz*i:blk_sz*i+blk_sz])
    
    return (G_mats, h_vecs)

def generate(self):
    """This function will make sure to check that all *vector* variables have
    their dimension defined. If dimensions are defined for SCALAR variables, 
    they are ignored."""
    codegen = self.codegen
    used = set(self.used_syms)
    
    # get the used params and the used variables
    params = dict( (k,v) for k,v in self.symtable.iteritems() if k in used and isinstance(v,Parameter) )
    variable_set = codegen.needed_variable_dims(used)
    
    # for the objective 
    c = codegen.obj.linfunc.linear_dict
    
    # these are the data matrices
    A, b, b_height = [], [], []
    Gl, hl, hl_height = [], [], []
    Gq, hq, hq_height = [], [], []
    # this is a block matrix for product cones
    Gblk, hblk, hblk_blocks = [], [], [] # these are for doing things like abs(x) <= t
    
    for k in codegen.cones:
        if k.size == 0:
            # print "goes in A,b"
            row, coeff, sizes = k.get_all_rows()
            A += row
            b += coeff
            b_height += sizes
        elif k.size == 1:
            # print "goes in Gl, hl"
            row, coeff, sizes = k.get_all_rows()
            Gl += row
            hl += coeff
            hl_height += sizes
        elif isinstance(k.size, int):
            # print "row-wise goes in Gblk,hblk"
            row, coeff, sizes = k.get_all_rows()
            Gblk.append(row)
            hblk.append(coeff)
            hblk_blocks.append(sizes)
        else:
            # print "concat in Gq,hq"
            row, coeff, sizes = k.get_all_rows()
            Gq.append(row)
            hq.append(coeff)
            hq_height.append(sizes)

    def solver(**kwargs):
        # we'll assume we know 
        # # keyword args expect values to be of type int
        if all(isinstance(e,int) or isinstance(e,o.matrix) for e in kwargs.values()):
            # args contains *actual* dimensions (for variables) and parameter values
            args = mangle(kwargs)
            
            # only care about the ones that are used
            # args = dict( (k,v) for k,v in mangled.iteritems() if k in set(used) )
            
            # make sure all keys are subset of needed variable list
            if variable_set.issubset(args) and set(params).issubset(args):
                # first, make sure all parameter arguments are sparse matrices
                for k in set(params):
                    if isinstance(args[k], float) or isinstance(args[k], int):
                        args[k] = o.spmatrix(args[k],[0],[0])
                    elif isinstance(args[k], o.matrix):
                        args[k] = o.sparse(args[k])
                                
                # get the size lookup table using actual dimensions
                sizes = codegen.get_variable_sizes(args)
                # build the location of the start indices from the size table
                start_idxs, cum = {}, 0
                for k,v in sizes.iteritems():
                    start_idxs[k] = cum
                    cum += v
                                
                # add parameter sizes to the dictionary (!!!hack)
                for k in codegen.parameters:
                    if k in set(args):
                        sizes[k] = args[k].size[0]
                
                # get objective vector
                c_obj = o.matrix(0, (cum,1), 'd')
                for k,v in c.iteritems():
                    # we ignore constant coefficients
                    if k != '1':
                        idx = start_idxs[k]
                        row_height = sizes[k]
                        c_obj[idx:idx+row_height] = eval_matrix_coeff(v, args, row_height, 1)
                
                # get matrices
                A_mat, b_mat = build_matrix(A, b, b_height, args, sizes, start_idxs, cum)
                Gl_mat, hl_vec = build_matrix(Gl, hl, hl_height, args, sizes, start_idxs, cum)
                Gq_mats, hq_vecs = [], []
                
                # matrices in SOC
                for G, h, height in zip(Gq, hq, hq_height):
                    mat, vec = build_matrix(G, h, height, args, sizes, start_idxs, cum)
                    # ensure that sizes agree
                    oldsize = mat.size
                    mat.size = (oldsize[0], cum)
                    Gq_mats.append(mat)
                    hq_vecs.append(vec)
                
                for G, h, height in zip(Gblk, hblk, hblk_blocks):
                    mats, vecs = build_block_matrices(G, h, height, args, sizes, start_idxs, cum)
                    # ensure that sizes agree
                    for m in mats:
                        oldsize = m.size
                        m.size = (oldsize[0], cum)
                    
                    Gq_mats += mats
                    hq_vecs += vecs
                
                sol = solvers.socp(c_obj, Gl_mat, hl_vec, Gq_mats, hq_vecs, A_mat, b_mat)
                # print sol
                # # Gl_mat, hl_vec
                # 
                # print sizes
                # print c_obj
                # print A_mat
                # print b_mat
                # print Gl_mat
                # print hl_vec
                # 
                #     
                # print c_obj
                return sol

            else:
                raise Exception("Not all variable dimensions or parameters have been specified.")
        else:
            raise Exception("Expected integer arguments for variables and matrix arguments for params.") 
    return solver
    
# TODO: attach generate to Scoop class
# def generate(self, *kwargs):
#     self.
#     
# # eventually will take Evaluator object or some IR as input
#     # do as much of the hard work outside of this function
#     # there's not a lot to be done, but the more you do, the better
#     
#     # this is a compromise with CVX and CVXGEN
#     #   * you won't have to re-parse the problem, but you do have to re-stuff
#     #   * you don't get the speed of CVXGEN, but you get the speed of programming (as in CVX)
#     def f(**kwargs):
#         # check to make sure the provided arguments are in our parameter list
#         # at the moment, this list is just provided by the args to generate
#         if set(args).issubset(kwargs):
#             print "Yay! it works!"
#         else:
#             print "You fail! We expected arguments named %s" % str(args)
#                # this function won't work because you passed the wrong arguments. we're expecting
#             raise Exception("SORRY!")
# 
#     # return the solver function
#    return f