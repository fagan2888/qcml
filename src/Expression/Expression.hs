module Expression.Expression (
  Curvature(..), 
  Monotonicity(..), 
  Sign(..), 
  Expr(..), 
  Parameter(..), 
  Symbol(..),
  applyDCP
) where
  
  -- data types
  data Curvature
    = Convex
    | Concave
    | Affine
    | Nonconvex
    deriving (Show, Eq)

  data Monotonicity
    = Increasing
    | Decreasing
    | Nonmonotone
    deriving (Show, Eq)

  data Sign
    = Positive
    | Negative
    | Unknown
    deriving (Show, Eq)

  data Expr
    = Expr String Curvature Sign (Int, Int)
    | Variable String (Int, Int)
    | None
   deriving (Show)

  data Parameter = Parameter String Sign (Int, Int) deriving (Show)
  
  -- type classes to enable vexity inference
  class Symbol a where
    name :: a -> String
    vexity :: a -> Curvature
    sign :: a -> Sign
    rows :: a -> Int
    cols :: a -> Int

  instance Symbol Expr where
    name None = ""
    name (Expr s _ _ _) = s
    name (Variable s _) = s
    
    vexity None = Nonconvex
    vexity (Variable _ _) = Affine
    vexity (Expr _ c _ _) = c
    
    sign None = Unknown
    sign (Variable _ _) = Unknown
    sign (Expr _ _ s _) = s
    
    rows None = 0
    rows (Expr _ _ _ (m,_)) = m
    rows (Variable _ (m,_)) = m
    
    cols None = 0
    cols (Expr _ _ _ (_,n)) = n
    cols (Variable _ (_,n)) = n

  instance Symbol Parameter where
    name (Parameter s _ _) = s
    vexity (Parameter _ _ _) = Affine
    sign (Parameter _ s _) = s
    rows (Parameter _ _ (m,_)) = m
    cols (Parameter _ _ (_,n)) = n

  -- DCP rules
  applyDCP :: Curvature -> Monotonicity -> Curvature -> Curvature
  applyDCP Convex Increasing Convex = Convex
  applyDCP Convex Decreasing Concave = Convex
  applyDCP Concave Decreasing Convex = Concave
  applyDCP Concave Increasing Concave = Concave
  applyDCP c _ Affine = c
  applyDCP Affine Increasing c = c
  applyDCP Affine Decreasing c = flipVexity c
  applyDCP _ _ _ = Nonconvex

  flipVexity :: Curvature -> Curvature
  flipVexity Concave = Convex
  flipVexity Convex = Concave
  flipVexity Affine = Affine
  flipVexity Nonconvex = Nonconvex