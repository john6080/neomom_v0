module zfill_m
    
!==============================================================================
!  zfill_m — EFIE wire MOM Z-matrix fill (Galerkin, rooftop basis functions)
!
!  Purpose:
!   Compute the complex N×N impedance matrix Z where N = number of rooftop
!   basis functions.  Called once per frequency by mesh_m::matrix_fill.
!
!==============================================================================
!  EFIE GALERKIN MATRIX ELEMENT
!==============================================================================
!
!  Z_mn = j*k*ETA0 * SUM_{p=1,2} SUM_{q=1,2} [ A_pq  -  (1/k²) * Phi_pq ]
!
!  p = test half index (1 or 2 of basis m)
!  q = source half index (1 or 2 of basis n)
!
!  Vector-potential term:
!    A_pq = effSign_p * effSign_q * (uHat_p · uHat_q)
!           * INT_{Sp} INT_{Sq} scalar_p(x) * scalar_q(x') * G(R) dx dx'
!
!  Scalar-potential (charge) term:
!    Phi_pq = div_p * div_q
!             * INT_{Sp} INT_{Sq} G(R) dx dx'
!
!  Free-space Green's function:
!    G(R) = exp(-j*k*R) / (4*π*R),   R = |r - r'|
!
!  The matrix is symmetric (Galerkin), so only the upper triangle is
!  computed in fill_matrix.  The lower triangle fill (commented out) must
!  be re-enabled, or the solver must accept an upper-triangle-only matrix.
!
!==============================================================================
!  INTERACTION CLASSIFICATION PER HALF-PAIR (Hp, Hq)
!==============================================================================
!
!  SELF  : Hp%iSeg == Hq%iSeg  (same segment, not an image term)
!    Source integral: Gibson thin-wire analytical formula (Section 4.5.2)
!    Test quadrature: NQ_NEAR (16-point) for accuracy near the singularity
!
!  NEAR  : Sp and Sq share at least one node  (adjacent segments)
!    Source integral: NQ_NEAR (16-point) Gauss-Legendre
!    Test quadrature: NQ_NEAR (16-point)
!    The near-singular 1/R behaviour at the shared node is integrable but
!    requires more points than the far case.
!
!  FAR   : all other pairs
!    Source integral: NQ_FAR (4-point) Gauss-Legendre
!    Test quadrature: NQ_FAR (4-point)
!
!==============================================================================
!  GIBSON THIN-WIRE SELF-TERM  (source_self_analytical)
!==============================================================================
!
!  For test point at position x along the self segment (wire radius a, length L):
!    R0 = sqrt(a² + x²)                 (distance from test pt to left end)
!    RL = sqrt(a² + (x-L)²)             (distance from test pt to right end)
!    arglog = log( (x+R0) / (x-L+RL) )
!
!    S1_asc  =  (RL/L - R0/L + x/L * arglog) - j*(k*L/2)   [Gibson 4.83]
!    S1_desc = -S1_asc + arglog - j*(k*L/2)                  [Gibson 4.85]
!    S2      = (1/L) * (arglog - j*k*L) * L                  [scalar potential]
!
!  S1_asc  corresponds to iEnd_q=2 (ascending source scalar x'/L)
!  S1_desc corresponds to iEnd_q=1 (descending source scalar (L-x')/L)
!  All results are divided by 4π before return.
!
!  Reference: Gibson, "The Method of Moments in Electromagnetics", 2nd ed.,
!  Section 4.5.2, Eqs. 4.83–4.86.
!
!==============================================================================
!  GROUND PLANE (image theory)
!==============================================================================
!
!  When zGroundRefl is present, a second pass over the (p,q) combinations is
!  made with useImage=.true.  The source segment is reflected: vSrc(3) → -vSrc(3).
!  For the uHat dot-product, the z-component of the source uHat is negated
!  (image of a z-current reverses sign; x,y-currents are unchanged).
!  The full Fresnel coefficient Refl = Γ multiplies the image contribution.
!  For PEC: Γ = -1 (vertical polarisation) → image current reverses sign.
!
!==============================================================================
!  QUADRATURE TABLES
!==============================================================================
!
!  4-point  (NQ_FAR):  standard GL on [0,1]
!  16-point (NQ_NEAR): generated from Quadrature_V2_m with nQ=16 (single prec.)
!    These are the validated values used throughout the solver.
!    The commented-out 16-point block above them was a placeholder and was
!    replaced with the Quadrature_V2_m output.
!
!==============================================================================
!  PREFACTOR CONVENTION
!==============================================================================
!
!  jkEta = j * k * ETA0   (ETA0 = 376.7303 Ω from basic_header_m)
!  G     = exp(-j*k*R) / (4*π*R)
!
!  ETA0 is the exact free-space wave impedance, NOT the approximation 120*π.
!  The commented-out line `eta0 = FOURPI * 30.0` (= 120*π ≈ 376.99 Ω)
!  must NOT be used; it differs from ETA0 by ~0.07% and breaks gain closure.
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m, only: SEGMENT_TYPE
   use basis_builder_m

   implicit none; private

   public :: ZFILL_TYPE

   !  NQ_FAR / NQ_NEAR: number of Gauss-Legendre quadrature points.
   !  Changing these requires matching updates to XI4/W4 and XI16/W16 tables.
   integer, parameter :: NQ_FAR  = 4    ! far-pair quadrature order
   integer, parameter :: NQ_NEAR = 16   ! near/self quadrature order


   !  4-point Gauss-Legendre nodes and weights on [0,1].
   !  Exact GL nodes mapped from standard [-1,1] interval.
   real, parameter :: XI4(4) = [ 0.069431844, 0.330009478, 0.669990522, 0.930568156 ]
   real, parameter :: W4(4)  = [ 0.173927423, 0.326072577, 0.326072577, 0.173927423 ]

   !  16-point Gauss-Legendre nodes and weights on [0,1].
   !  Generated by Quadrature_V2_m::Quad_GAUSS_Init(gQ, 16, cNEAR), single precision.
   !  These are the validated production values.  The earlier placeholder block
   !  (commented out above in the original source) had incorrect values and must
   !  not be used.
   real, parameter :: XI16(16) = [ &
      5.2995323E-03, 2.7712489E-02, 6.7184396E-02, 0.1222978, 0.1910619, &
      0.2709916,     0.3591982,     0.4524938,     0.5475063, 0.6408018, &
      0.7290084,     0.8089381,     0.8777022,     0.9328156, 0.9722875, &
      0.9947005 ]

   real, parameter :: W16(16) = [ &
      1.3576230E-02, 3.1126762E-02, 4.7579255E-02, 6.2314484E-02, 7.4797995E-02, &
      8.4578261E-02, 9.1301709E-02, 9.4725303E-02, 9.4725303E-02, 9.1301709E-02, &
      8.4578261E-02, 7.4797995E-02, 6.2314484E-02, 4.7579255E-02, 3.1126762E-02, &
      1.3576230E-02 ]


!------------------------------------------------------------------------------
!  ZFILL_TYPE: object wrapper for the Z-matrix fill routines.
!
!  initialized -- placeholder flag; never set .true. in current code.
!                 Reserved for future lazy-initialisation of quadrature tables.
!
!  Procedure structure:
!   fill_matrix             (public)  -- outer m,n,p,q loops; calls Z_half_pair
!   Z_half_pair             (private) -- one test/source half-pair → Z contribution
!   source_gauss            (private) -- Gauss source integration over Sq
!   source_self_analytical  (private) -- Gibson analytical source self-term
!------------------------------------------------------------------------------
   type :: ZFILL_TYPE
      logical :: initialized = .false.
   contains
      procedure          :: fill_matrix
      procedure, private :: Z_half_pair
      procedure, private :: source_gauss
      procedure, private :: source_self_analytical
   end type ZFILL_TYPE


contains

!==============================================================================
!  fill_matrix: public entry point — assemble the full N×N Z matrix.
!
!  Input:
!   Basis(:)     -- rooftop basis functions (from basis_builder_m)
!   Segs(:)      -- mesh segments (from nodes_wires_segments_m)
!   Bk           -- free-space wave number k = 2π/λ  [1/m]
!   zGroundRefl  -- optional Fresnel reflection coefficient Γ for ground image.
!                   If absent or |Γ|=0, free-space only.
!
!  Output:
!   zMat(nB, nB) -- complex impedance matrix.
!
!  Only the UPPER triangle (m ≤ n) is filled.
!  The lower triangle assignment (zMat(n,m) = Zmn) is currently commented out.
!  If the solver requires a full matrix, uncomment that line.
!
!  For each (m, n) pair, Z_mn = sum over p=1,2 (test halves) and q=1,2
!  (source halves) of both the direct and image contributions.
!==============================================================================
   subroutine fill_matrix(this, Basis, Segs, Bk, zMat, zGroundRefl)

   !use zfill_nec_m

      class(ZFILL_TYPE),    intent(inout)        :: this
      type(BASIS2_TYPE),    intent(in)           :: Basis(:)
      type(SEGMENT_TYPE),   intent(in)           :: Segs(:)
      real,                 intent(in)           :: Bk
      complex, allocatable, intent(out)          :: zMat(:,:)
      complex, optional,    intent(in)           :: zGroundRefl   ! Γ for image terms

      
      integer :: nB, m, n, p, q
      complex :: Zmn, Refl
      logical :: hasGround

    !subroutine fill_matrix_nec(this, Basis, Segs, Bk, zMat, zGroundRefl)
     
     ! call zNEC%fill_matrix_nec( Basis, Segs, Bk, zMat, zGroundRefl )
      
     ! RETURN
      
      
      nB = size(Basis)
      allocate(zMat(nB, nB))
      zMat = zZERO

      hasGround = present(zGroundRefl)
      Refl      = zZERO
      if (hasGround) Refl = zGroundRefl

      write(*,'(a,i6,a)') '  fill_matrix: filling ', nB, 'x'//trim(str(nB))//' Z matrix'

      do m = 1, nB
         do n = m, nB    ! upper triangle only (Galerkin: Z is symmetric)

            Zmn = zZERO

            ! Direct (free-space) contribution: 2×2 half-pair combinations
            do p = 1, 2
               do q = 1, 2
                  Zmn = Zmn + this%Z_half_pair( &
                           Basis(m)%half(p), Basis(n)%half(q), &
                           Basis(m)%radius,  Segs, Bk,         &
                           useImage=.false., Refl=zZERO )
               end do
            end do

            ! Ground plane image contribution (only if ground is present)
            if (hasGround .and. abs(Refl) > ZERO) then
               do p = 1, 2
                  do q = 1, 2
                     Zmn = Zmn + this%Z_half_pair( &
                              Basis(m)%half(p), Basis(n)%half(q), &
                              Basis(m)%radius,  Segs, Bk,         &
                              useImage=.true.,  Refl=Refl )
                  end do
               end do
            end if

            zMat(m, n) = Zmn
            !zMat(n, m) = Zmn    ! Galerkin symmetry — uncomment for full matrix

         end do
      end do

   end subroutine fill_matrix


!==============================================================================
!  Z_half_pair: contribution of one (test half Hp, source half Hq) pair to Z_mn.
!
!  Classifies the interaction (SELF / NEAR / FAR), selects quadrature order,
!  runs the outer (test) quadrature loop, and assembles the EFIE formula.
!
!  Classification:
!   SELF  = Hp%iSeg == Hq%iSeg  AND  useImage==.false.
!   NEAR  = segments share a node  AND  not self
!   FAR   = all other pairs
!
!  uHat dot product for image source:
!   Image flips the z-component of the source uHat.
!   uDotu = ux_p*ux_q + uy_p*uy_q - uz_p*uz_q   (note the minus sign)
!
!  EFIE assembly:
!   A_pq   = effSign_p * effSign_q * uDotu * (quadrature sum for A integral)
!   Phi_pq = div_p * div_q          *        (quadrature sum for Phi integral)
!   Z      = zSign * j*k*ETA0 * (A_pq - Phi_pq / k²)
!   where zSign = 1 for direct, Γ for image.
!
!  Note: the commented-out `eta0 = FOURPI*30.0` line must NOT be used.
!  The active code correctly uses ETA0 from basic_header_m.
!==============================================================================
   function Z_half_pair(this, Hp, Hq, wireRadius, Segs, Bk, useImage, Refl) result(Z)

      class(ZFILL_TYPE),  intent(inout) :: this
      type(HALF_TYPE),    intent(in)    :: Hp          ! test half (basis m, half p)
      type(HALF_TYPE),    intent(in)    :: Hq          ! source half (basis n, half q)
      real,               intent(in)    :: wireRadius  ! wire radius for self-term [m]
      type(SEGMENT_TYPE), intent(in)    :: Segs(:)
      real,               intent(in)    :: Bk          ! k = 2π/λ [1/m]
      logical,            intent(in)    :: useImage    ! .true. = reflect source at z=0
      complex,            intent(in)    :: Refl        ! Fresnel Γ (used if useImage)
      complex                           :: Z

      type(SEGMENT_TYPE) :: Sp, Sq
      logical  :: isSelf, isNear
      integer  :: ip, nQtest
      real     :: xTest, Lp, scalar_p, uDotu
      real     :: vTest(3)
      complex  :: Ivec, Iscl, A_pq, Phi_pq, jkEta, zSign

      Sp = Segs(Hp%iSeg)
      Sq = Segs(Hq%iSeg)

      ! Interaction type
      isSelf = (Hp%iSeg == Hq%iSeg) .and. (.not. useImage)
      isNear = segments_share_node(Sp, Sq) .and. (.not. isSelf)

      ! EFIE prefactor: j*k*ETA0  (ETA0 = 376.7303 Ω, exact — not 120π)
      jkEta = zIMAG * Bk * ETA0

      ! Image sign: zSign = Γ for image terms, 1 for direct
      zSign = zONE
      if (useImage) zSign = Refl

      ! uHat dot product; z-component of source uHat negated for image
      uDotu = dot_product(Sp%uHat, Sq%uHat)
      if (useImage) then
         uDotu = Sp%uHat(1)*Sq%uHat(1) &
               + Sp%uHat(2)*Sq%uHat(2) &
               - Sp%uHat(3)*Sq%uHat(3)   ! z-term negated for image
      end if

      Lp     = Sp%length
      nQtest = NQ_FAR
      if (isSelf .or. isNear) nQtest = NQ_NEAR   ! more test points near singularity

      A_pq   = zZERO
      Phi_pq = zZERO

      ! Outer (test) quadrature loop over segment Sp
      do ip = 1, nQtest

         xTest  = xi_n(ip, nQtest) * Lp                    ! position along Sp [0..Lp]
         vTest  = Sp%vNodes(:,1) + xTest * Sp%uHat          ! 3-D test point
         scalar_p = scalar_fn(xTest, Lp, Hp%iEnd)           ! test shape function value

         ! Source integration: analytical for self, Gauss for near/far
         if (isSelf) then
            call this%source_self_analytical(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
         else
            call this%source_gauss(vTest, Sq, Bk, Hq%iEnd, isNear, useImage, Ivec, Iscl)
         end if

         ! Accumulate weighted integrals
         A_pq   = A_pq   + w_n(ip, nQtest) * Lp * scalar_p * Ivec
         Phi_pq = Phi_pq + w_n(ip, nQtest) * Lp             * Iscl

      end do

      ! Apply basis-function signs and geometric weights
      A_pq   = Hp%effSign * Hq%effSign * uDotu * A_pq   ! vector potential
      Phi_pq = Hp%div     * Hq%div              * Phi_pq ! scalar potential (charge)

      ! EFIE: Z = zSign * j*k*ETA0 * (A - Phi/k²)
      Z = zSign * jkEta * (A_pq - Phi_pq / (Bk * Bk))

   end function Z_half_pair


!==============================================================================
!  source_gauss: numerical Gauss-Legendre source integration over segment Sq.
!
!  Returns:
!   Ivec = INT_{Sq} scalar_q(x') * G(R) dx'   [vector-potential weight]
!   Iscl = INT_{Sq} G(R) dx'                   [scalar-potential weight]
!
!  Quadrature order: NQ_NEAR for adjacent (isNear=.true.), NQ_FAR otherwise.
!
!  Image: if useImage=.true., the source point is reflected to z → -z before
!  computing R.  The weight w*Lq is absorbed into Green to keep Ivec/Iscl as
!  pure integrals; the caller does NOT apply an additional Lq factor.
!
!  R guard: R < 1e-12 is clamped to 1e-12 to prevent divide-by-zero.
!  This should not occur for non-self pairs, but provides safety against
!  coincident centroids after poor meshing.
!==============================================================================
   subroutine source_gauss(this, vTest, Sq, Bk, iEnd_q, isNear, useImage, Ivec, Iscl)

      class(ZFILL_TYPE),  intent(in)  :: this
      real,               intent(in)  :: vTest(3)     ! test point [m]
      type(SEGMENT_TYPE), intent(in)  :: Sq           ! source segment
      real,               intent(in)  :: Bk
      integer,            intent(in)  :: iEnd_q       ! 1=descending, 2=ascending
      logical,            intent(in)  :: isNear       ! use NQ_NEAR points?
      logical,            intent(in)  :: useImage     ! reflect source at z=0?
      complex,            intent(out) :: Ivec, Iscl

      integer :: iq, nQsrc
      real    :: xSrc, Lq, R, scalar_q
      real    :: vSrc(3), vSrcImg(3), vR(3)
      complex :: Green

      nQsrc = NQ_FAR
      if (isNear) nQsrc = NQ_NEAR

      Lq   = Sq%length
      Ivec = zZERO
      Iscl = zZERO

      do iq = 1, nQsrc

         xSrc = xi_n(iq, nQsrc) * Lq                       ! position along Sq [0..Lq]
         vSrc = Sq%vNodes(:,1) + xSrc * Sq%uHat            ! 3-D source point

         ! For image, reflect the source point below the ground plane
         if (useImage) then
            vSrcImg    = vSrc
            vSrcImg(3) = -vSrc(3)
            vR = vTest - vSrcImg
         else
            vR = vTest - vSrc
         end if

         R = norm2(vR)
         if (R < 1.0e-12) R = 1.0e-12   ! safety guard (non-self; should not trigger)

         ! Green's function weighted by quadrature weight and Lq
         Green = w_n(iq, nQsrc) * Lq * exp(-zIMAG*Bk*R) / (FOURPI * R)

         scalar_q = scalar_fn(xSrc, Lq, iEnd_q)   ! source shape function value

         Ivec = Ivec + scalar_q * Green   ! vector-potential contribution
         Iscl = Iscl +            Green   ! scalar-potential contribution

      end do

   end subroutine source_gauss


!==============================================================================
!  source_self_analytical: Gibson thin-wire self-term (Section 4.5.2).
!
!  Evaluates the source integral analytically for a test point at position x
!  along its own segment (same segment as source).  Avoids the 1/R singularity
!  by using the exact near-field formula for a straight thin wire.
!
!  Input:
!   x     -- test position along the segment, measured from left node [0..L]
!   a     -- wire radius [m]
!   L     -- segment length [m]
!   iEnd_q -- source half type: 2=ascending (x'/L), 1=descending ((L-x')/L)
!   Bk    -- wave number k
!
!  Output:
!   Ivec  -- source integral weighted by the scalar basis function (÷4π)
!   Iscl  -- unweighted source integral (÷4π), for scalar-potential term
!
!  Derivation variables:
!   R0     = sqrt(a² + x²)       distance from x to left endpoint (x'=0)
!   RL     = sqrt(a² + (x-L)²)   distance from x to right endpoint (x'=L)
!   arglog = log((x+R0)/(x-L+RL))
!
!   arglog denominator guard: max(|x-L+RL|, 1e-30) prevents log(∞) when
!   a→0 at x=0 exactly.  In practice for finite a>0, x-L+RL = -L+sqrt(a²+L²)
!   which stays positive, but the guard protects against a=0 inputs.
!
!  Reference: Gibson, "The Method of Moments in Electromagnetics", 2nd ed.,
!  Section 4.5.2, Eqs. 4.83–4.86.
!==============================================================================
   subroutine source_self_analytical(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(ZFILL_TYPE), intent(in)  :: this
      real,              intent(in)  :: x       ! test position [0..L]
      real,              intent(in)  :: a       ! wire radius [m]
      real,              intent(in)  :: L       ! segment length [m]
      integer,           intent(in)  :: iEnd_q  ! 1=descending, 2=ascending source
      real,              intent(in)  :: Bk
      complex,           intent(out) :: Ivec, Iscl

      real    :: R0, RL, arglog
      complex :: S1_asc, S1_desc, S2

      R0     = sqrt(a*a + x*x)
      RL     = sqrt(a*a + (x - L)*(x - L))

      ! arglog = log((x+R0) / (x-L+RL)); guard denominator against zero
      arglog = log( (x + R0) / max(abs(x - L + RL), 1.0e-30) )

      ! Vector-potential source integrals (Gibson 4.83, 4.85)
      S1_asc  =  (RL/L - R0/L + (x/L)*arglog) - zIMAG*(Bk*L/2.0)   ! iEnd_q=2
      S1_desc = -(RL/L - R0/L + (x/L)*arglog) - zIMAG*(Bk*L/2.0) + arglog  ! iEnd_q=1

      ! Scalar-potential (unweighted G) source integral (Gibson 4.86)
      S2 = (ONE/L) * (arglog - zIMAG*(Bk*L))   ! per unit length; *L below

      ! Normalise by 4π (matches G = exp(-jkR)/(4π*R) convention)
      S1_asc  = S1_asc  / FOURPI
      S1_desc = S1_desc / FOURPI
      S2      = S2 * L  / FOURPI    ! restore L factor so Iscl = INT G dx' / (4π)

      Ivec = merge(S1_asc, S1_desc, iEnd_q == 2)
      Iscl = S2

   end subroutine source_self_analytical


!==============================================================================
!  Helper functions (all pure, no side effects)
!==============================================================================

   !  scalar_fn: rooftop shape function value at position x on segment of length L.
   !   iEnd==2: ascending  f = x/L     (0 at left, 1 at hub=right)
   !   iEnd==1: descending f = (L-x)/L (1 at hub=left, 0 at right)
   pure real function scalar_fn(x, L, iEnd)
      real,    intent(in) :: x, L
      integer, intent(in) :: iEnd
      if (iEnd == 2) then
         scalar_fn = x / L
      else
         scalar_fn = (L - x) / L
      end if
   end function scalar_fn

   !  segments_share_node: .true. if Sp and Sq have at least one node in common.
   !  Checks all four left/right combinations.
   pure logical function segments_share_node(Sp, Sq)
      type(SEGMENT_TYPE), intent(in) :: Sp, Sq
      segments_share_node = &
         (Sp%iLeftNode  == Sq%iLeftNode)  .or. &
         (Sp%iLeftNode  == Sq%iRightNode) .or. &
         (Sp%iRightNode == Sq%iLeftNode)  .or. &
         (Sp%iRightNode == Sq%iRightNode)
   end function segments_share_node

   !  xi_n: quadrature node i for a rule of order nQ.
   !  Dispatches between the 4-point (NQ_FAR) and 16-point (NQ_NEAR) tables.
   pure real function xi_n(i, nQ)
      integer, intent(in) :: i, nQ
      if (nQ == NQ_FAR) then
         xi_n = XI4(i)
      else
         xi_n = XI16(i)
      end if
   end function xi_n

   !  w_n: quadrature weight i for a rule of order nQ.
   pure real function w_n(i, nQ)
      integer, intent(in) :: i, nQ
      if (nQ == NQ_FAR) then
         w_n = W4(i)
      else
         w_n = W16(i)
      end if
   end function w_n

   !  str: integer to left-adjusted string.
   !  Avoids compiler-specific write-to-character quirks in the fill_matrix banner.
   pure function str(n) result(s)
      integer, intent(in) :: n
      character(len=12) :: s
      write(s,'(i0)') n
      s = adjustl(s)
   end function str

end module zfill_m
