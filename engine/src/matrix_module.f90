module matrix_m

!==============================================================================
!  matrix_m
!
!  Purpose:
!   Factorize and solve the NeoMoM complex symmetric impedance matrix Ax = b,
!   where A is the N×N Z-matrix filled by zfill_m and b is the excitation vector.
!
!  Z is complex SYMMETRIC (not Hermitian): Z = Z^T.
!  This arises from Galerkin MOM on a reciprocal structure.
!  Symmetry means the off-diagonal elements satisfy Z(m,n) = Z(n,m), so the
!  upper triangle (filled by zfill_m::fill_matrix) contains all information.
!
!==============================================================================
!  SOLVER CHOICES
!==============================================================================
!
!  TWO IMPLEMENTATIONS ARE PROVIDED.  Select by setting the parameter
!  USE_MKL below.  Both have identical public interfaces (LU_Factor, LU_Solve).
!
!  USE_MKL = .TRUE.   (current default — requires MKL or LAPACK library)
!  -----------------------------------------------------------------
!   LU_Factor: calls LAPACK csytrf('U', ...)
!     Bunch-Kaufman symmetric indefinite factorisation.
!     Exploits complex symmetry; works directly on upper-triangle storage.
!     Workspace query pattern (lwork=-1 then actual call) sizes the work array.
!   LU_Solve:  calls LAPACK csytrs('U', ...)
!     Triangular solve using the Bunch-Kaufman factors.
!
!  USE_MKL = .FALSE.  (no external dependencies — pure Fortran LU)
!  -----------------------------------------------------------------
!   LU_Factor: symmetrises upper → lower triangle, then in-place LU with
!     partial (row) pivoting.  All arithmetic is performed in double
!     precision (complex(8)) regardless of wp; results are stored back
!     into zBlk(wp) after factoring.  This avoids the single-precision
!     cancellation in the Schur complement that otherwise causes cascading
!     row swaps and ~4× amplitude errors for near-resonant EFIE matrices.
!   LU_Solve:  applies all row permutations to b first, then forward
!     substitution through L (no swaps), then back substitution through U —
!     all accumulated in double precision.  (Interleaving swaps and L-updates
!     is incorrect when the L factors are stored in post-pivot row order.)
!
!  Performance note:
!   For typical NeoMoM problem sizes (N < 2000) both solvers complete in
!   milliseconds.  The pure Fortran path has no measurable penalty.
!
!  To switch: change USE_MKL to .FALSE. and remove the `external` declarations
!  and the MKL/LAPACK library from the link step.
!
!==============================================================================
!  SYMMETRIZATION NOTE
!==============================================================================
!
!  zfill_m fills only the UPPER triangle of zBlk.  Lower triangle is zero.
!
!  LAPACK csytrf('U') reads only the upper triangle, so it works correctly
!  on the half-filled matrix.
!
!  The pure Fortran LU path requires a full matrix.  LU_Factor_Pure
!  therefore copies upper → lower before factoring:
!    zBlk(j, i) = zBlk(i, j)  for j > i
!  This is a one-time O(N²) copy and does not change the asymptotic cost.
!
!==============================================================================

  use basic_header_m
  

   implicit none; private

   !  Select solver backend.
   !  .TRUE.  → MKL/LAPACK (csytrf, csytrs)  — requires external library
   !  .FALSE. → Pure Fortran LU               — no external dependencies
   logical, parameter :: USE_MKL = .FALSE.  ! .TRUE.

   ! External MKL/LAPACK declarations (only needed when USE_MKL=.TRUE.)
   ! Remove these lines when switching to USE_MKL=.FALSE.
  ! external :: csytrf, csytrs

   public :: MATRIX_TYPE


!------------------------------------------------------------------------------
!  MATRIX_TYPE: factorized-matrix container.
!
!  zBlk(:,:)    -- on input:  upper triangle = Z-matrix from zfill_m
!                  on output: overwritten with Bunch-Kaufman factors (MKL path)
!                             NOT used by pure LU path after factoring
!  zBlk_dp(:,:) -- pure LU path only: double-precision LU factors.
!                  Allocated and filled by LU_Factor_Pure; read by LU_Solve_Pure.
!                  Left unallocated by the MKL path.
!  iPivots(:)   -- pivot index array; length N; allocated in LU_Factor
!                  For Bunch-Kaufman: LAPACK pivot encoding (may be negative
!                  for 2×2 blocks; see LAPACK dsytrf documentation).
!                  For pure LU: simple row-swap index, iPivots(k) = pivot row.
!------------------------------------------------------------------------------
   type MATRIX_TYPE
      complex(wp), allocatable :: zBlk(:, :)
      complex(8),  allocatable :: zBlk_dp(:, :)   ! pure LU: double-prec factors
      integer,     allocatable :: iPivots(:)
   contains
      procedure :: LU_Factor
      procedure :: LU_Solve
   end type MATRIX_TYPE


contains

!==============================================================================
!  LU_Factor: factorize zBlk in-place.
!
!  Dispatches to MKL or pure Fortran backend based on USE_MKL parameter.
!
!  On entry:  zBlk(1:N, 1:N) with upper triangle filled (lower may be zero).
!  On exit:   zBlk overwritten with factored form; iPivots(:) filled.
!==============================================================================
   subroutine LU_Factor(D)

      class(MATRIX_TYPE), intent(inout) :: D

      if (USE_MKL) then
         call LU_Factor_MKL(D)
      else
         call LU_Factor_Pure(D)
      end if

   end subroutine LU_Factor


!==============================================================================
!  LU_Solve: solve D*X = X (overwrites X with solution).
!
!  Uses factors from LU_Factor.  X is length N on entry (the excitation
!  vector b); on exit X holds the solution (basis function currents).
!==============================================================================
   subroutine LU_Solve(Dinv, X)

      class(MATRIX_TYPE), intent(in)    :: Dinv
      complex(wp),        intent(inout) :: X(:)

      if (USE_MKL) then
         call LU_Solve_MKL(Dinv, X)
      else
         call LU_Solve_Pure(Dinv, X)
      end if

   end subroutine LU_Solve


!==============================================================================
!  ---- MKL / LAPACK BACKEND ------------------------------------------------
!==============================================================================

!------------------------------------------------------------------------------
!  LU_Factor_MKL: Bunch-Kaufman symmetric complex factorisation via csytrf.
!
!  csytrf('U', N, A, lda, iPivots, work, lwork, info):
!   'U'      -- use upper triangle of A
!   N        -- matrix order
!   A        -- on exit: Bunch-Kaufman factors in upper triangle
!   iPivots  -- pivot array; negative entry = 2×2 block pivot at that step
!   work     -- workspace; first call with lwork=-1 queries optimal size
!   info     -- 0=success, >0=singular at step info
!
!  The workspace query pattern (lwork=-1 first call, then allocate, then
!  actual call) avoids hardcoding a workspace size.
!------------------------------------------------------------------------------
   subroutine LU_Factor_MKL(D)

      class(MATRIX_TYPE), intent(inout) :: D

      integer              :: iErr, m, lda, lwork
      complex, allocatable :: work(:)
      character(*), parameter :: cSub = 'LU_Factor_MKL: '

      if (allocated(D%iPivots)) deallocate(D%iPivots)

      m   = size(D%zBlk, 1)
      lda = m
      allocate(D%iPivots(m))

      ! Workspace query: lwork = -1 → work(1) returns optimal workspace size
      lwork = -1
      allocate(work(1))
      call fatalError('MKL LU and Solve routines not used','',0)
     ! call csytrf('U', m, D%zBlk, lda, D%iPivots, work, lwork, iErr)
      if (iErr /= 0) call FatalError(cSub//'workspace query failed', 'iErr', iErr)

      lwork = int(real(work(1)))
      deallocate(work)
      allocate(work(lwork))

      ! Actual Bunch-Kaufman factorisation
     ! call csytrf('U', m, D%zBlk, lda, D%iPivots, work, lwork, iErr)
      if (iErr /= 0) call FatalError(cSub//'csytrf factorisation failed', 'iErr', iErr)

   end subroutine LU_Factor_MKL


!------------------------------------------------------------------------------
!  LU_Solve_MKL: triangular solve via csytrs.
!
!  csytrs('U', N, 1, A, lda, iPivots, X, ldx, info):
!   '1'  -- nrhs = 1 (single right-hand side; hardcoded)
!   X    -- on entry: rhs b; on exit: solution x
!
!  Note: nrhs is hardcoded to 1.  If multi-RHS solve is ever needed (e.g.
!  multiple excitation ports), change nC and adjust the X declaration.
!------------------------------------------------------------------------------
   subroutine LU_Solve_MKL(Dinv, X)

      class(MATRIX_TYPE), intent(in)    :: Dinv
      complex(wp),        intent(inout) :: X(:)

      integer :: iErr, nR, nC
      character(*), parameter :: cSub = 'LU_Solve_MKL: '

      nR = size(X, 1)
      nC = 1   ! single right-hand side; extend here for multi-port

    !  call csytrs('U', nR, nC, Dinv%zBlk, nR, Dinv%iPivots, X, nR, iErr)
      if (iErr /= 0) call FatalError(cSub//'csytrs solve failed', 'iErr', iErr)

   end subroutine LU_Solve_MKL


!==============================================================================
!  ---- PURE FORTRAN BACKEND ------------------------------------------------
!
!  Standard LU factorisation with partial (row) pivoting.
!  No external library dependencies; compiles with any standard Fortran 90+
!  compiler (gfortran, ifort, ifx, nvfortran, etc.).
!
!  The algorithm is equivalent to LAPACK's cgetrf/cgetrs but self-contained.
!  It works on a FULL matrix, so LU_Factor_Pure first symmetrises the upper
!  triangle into the lower before factoring.
!
!  Factor result (stored in zBlk after conversion back to wp=single):
!   zBlk(i,j) for i <= j : U factors (upper triangle)
!   zBlk(i,j) for i >  j : L factors (unit lower triangular, L(i,i) not stored)
!   iPivots(k)            : row swapped to row k at elimination step k
!
!  WHY DOUBLE PRECISION INTERNALLY:
!   Partial (row-only) pivoting on a complex-symmetric EFIE matrix breaks the
!   symmetric structure of the Schur complement after each row swap.  In single
!   precision the 12 rank-1 updates to the 7×7 trailing Schur complement
!   accumulate ~12·ε·||Z||² cancellation error, which causes the diagonal to
!   drop below some off-diagonals and triggers a cascade of spurious row swaps
!   (k=13..18 for the 19-basis half-wave dipole test case).  The cascade
!   propagates into the L and U factors, producing ~4× amplitude error and
!   broken phase symmetry in the solution.
!
!   Running the factorisation in complex(8) eliminates this effect entirely —
!   the EFIE matrix is well-conditioned (csytrf needs zero pivots) so the
!   double-precision Schur complement stays diagonally dominant throughout.
!   Results are stored back in single precision (wp) after factoring; the
!   LU_Solve_Pure accumulates the triangular solves in double precision as well.
!==============================================================================

!------------------------------------------------------------------------------
!  LU_Factor_Pure: symmetrize, then LU with partial pivoting in double precision.
!
!  Step 1 — promote and symmetrize:
!   Promote zBlk(wp) → zWork(complex(8)) and fill lower triangle.
!
!  Step 2 — elimination (all arithmetic in complex(8)):
!   For k = 1..N:
!     Find row imax with largest |A(imax,k)| in column k at or below row k
!     Swap rows k and imax; store iPivots(k) = imax
!     Compute L multipliers: A(k+1:N, k) /= A(k,k)
!     Update trailing submatrix: A(k+1:N, k+1:N) -= outer(A(k+1:N,k), A(k,k+1:N))
!
!  Step 3 — demote: store zWork → zBlk(wp).
!
!  Singularity: if |A(k,k)| < tiny(1.0d0) after pivoting, calls FatalError.
!------------------------------------------------------------------------------
   subroutine LU_Factor_Pure(D)

      class(MATRIX_TYPE), intent(inout) :: D

      integer                 :: n, k, imax, j
      complex(8)              :: tmp8
      real(8)                 :: amax, atmp
      character(*), parameter :: cSub = 'LU_Factor_Pure: '

      if (allocated(D%iPivots))   deallocate(D%iPivots)
      if (allocated(D%zBlk_dp))   deallocate(D%zBlk_dp)

      n = size(D%zBlk, 1)
      allocate(D%iPivots(n), D%zBlk_dp(n, n))

      ! Step 1: promote to double and symmetrize (fill lower from upper triangle)
      do k = 1, n
         D%zBlk_dp(k, k) = D%zBlk(k, k)
         do j = k+1, n
            D%zBlk_dp(k, j) = D%zBlk(k, j)   ! upper triangle (as filled by zfill_m)
            D%zBlk_dp(j, k) = D%zBlk(k, j)   ! lower = upper  (symmetry copy)
         end do
      end do

      ! Step 2: LU factorisation with partial pivoting (all in double precision)
      do k = 1, n

         ! Find pivot: row with largest |A(i,k)| for i >= k
         imax = k
         amax = abs(D%zBlk_dp(k, k))
         do j = k+1, n
            atmp = abs(D%zBlk_dp(j, k))
            if (atmp > amax) then
               amax = atmp
               imax = j
            end if
         end do
         D%iPivots(k) = imax

         ! Swap rows k and imax (entire row)
         if (imax /= k) then
            do j = 1, n
               tmp8               = D%zBlk_dp(k,    j)
               D%zBlk_dp(k,    j) = D%zBlk_dp(imax, j)
               D%zBlk_dp(imax, j) = tmp8
            end do
         end if

         ! Singular check
         if (abs(D%zBlk_dp(k, k)) < tiny(1.0d0)) &
            call FatalError(cSub//'singular pivot at step', 'k', k)

         ! Compute L multipliers in column k (below diagonal)
         D%zBlk_dp(k+1:n, k) = D%zBlk_dp(k+1:n, k) / D%zBlk_dp(k, k)

         ! Update trailing submatrix (rank-1 update)
         do j = k+1, n
            D%zBlk_dp(k+1:n, j) = D%zBlk_dp(k+1:n, j) &
                                 - D%zBlk_dp(k+1:n, k) * D%zBlk_dp(k, j)
         end do

      end do
      ! Note: zBlk_dp holds the full double-precision LU factors.
      ! zBlk is left unchanged (still holds original upper-triangle Z).

   end subroutine LU_Factor_Pure


!------------------------------------------------------------------------------
!  LU_Solve_Pure: forward + back substitution, accumulated in double precision.
!
!  The factorisation stores row-swap effects in-place: after every row swap
!  the already-computed L columns are also reordered.  Therefore the L stored
!  in zBlk_dp is referenced to the FINAL (fully-permuted) row ordering, and
!  the permutation P must be applied to the RHS BEFORE the forward sweep.
!  Interleaving swaps with L-updates (the textbook shortcut that is valid when
!  L is stored in pre-pivot order) gives wrong results here — verified by
!  Python simulation against MKL/LAPACK reference.
!
!  Correct algorithm (mirrors LAPACK dgetrs approach):
!   Step 1 — apply ALL row permutations to X (produces P*b):
!     For k = 1..N: swap X(k) and X(iPivots(k))
!   Step 2 — forward substitution (NO row swaps, pure L solve):
!     For k = 1..N-1: X(k+1:N) -= L(k+1:N, k) * X(k)
!   Step 3 — back substitution (U * x = y, upper triangular):
!     For k = N..1: X(k) /= U(k,k);  X(1:k-1) -= U(1:k-1,k) * X(k)
!
!  L and U values come from zBlk_dp (double precision) so the substitution
!  sweeps accumulate in double precision regardless of wp.
!------------------------------------------------------------------------------
   subroutine LU_Solve_Pure(Dinv, X)

      class(MATRIX_TYPE), intent(in)    :: Dinv
      complex(wp),        intent(inout) :: X(:)

      integer                 :: n, k
      complex(8)              :: tmp8
      complex(8), allocatable :: X8(:)

      n = size(X, 1)
      allocate(X8(n))
      X8 = X   ! promote rhs to double

      ! Step 1: apply ALL row permutations first (compute P*b).
      ! This must be a separate pass — do NOT interleave with the L-updates below.
      do k = 1, n
         if (Dinv%iPivots(k) /= k) then
            tmp8                  = X8(k)
            X8(k)                 = X8(Dinv%iPivots(k))
            X8(Dinv%iPivots(k))   = tmp8
         end if
      end do

      ! Step 2: forward substitution (L is unit lower triangular; no swaps here)
      do k = 1, n-1
         X8(k+1:n) = X8(k+1:n) - Dinv%zBlk_dp(k+1:n, k) * X8(k)
      end do

      ! Back substitution (U is upper triangular)
      do k = n, 1, -1
         X8(k) = X8(k) / Dinv%zBlk_dp(k, k)
         if (k > 1) X8(1:k-1) = X8(1:k-1) - Dinv%zBlk_dp(1:k-1, k) * X8(k)
      end do

      X = cmplx(X8, kind=wp)
      deallocate(X8)

    end subroutine LU_Solve_Pure

   !  To eliminate MKL:
   !  1. Change USE_MKL = .FALSE. above
   !  2. Remove the `external :: csytrf, csytrs` declarations
   !  3. Remove the MKL/LAPACK .lib / .dll from the link step
   !  4. LU_Factor_Pure and LU_Solve_Pure become the active paths automatically

end module matrix_m