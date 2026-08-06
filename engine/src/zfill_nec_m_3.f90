module zfill_nec_m

!==============================================================================
!  zfill_nec_m — NEC5-style wire-wire interaction fill (companion to zfill_m)
!
!  CORRECTION (v2): an earlier version of this module offered a "point
!  matching" mode as a supposed NEC5 differentiator. That was wrong. Per
!  Burke, "Accuracy of Reduced and Extended Thin-Wire Kernels" (LLNL-PROC-
!  409033): NEC-4 is point matched; NEC-5 is "a mixed potential code with
!  triangular and roof-top basis functions" -- i.e. Galerkin, the same
!  architecture family zfill_m already uses. That mode has been removed.
!  fill_matrix_nec below is plain double-integral Galerkin, same structure
!  as zfill_m::fill_matrix.
!
!  What actually distinguishes NEC5's wire-wire interaction is the KERNEL:
!  it offers a choice of RTWK (reduced thin-wire kernel) or ETWK (extended
!  thin-wire kernel). Both approximate the same exact kernel
!
!      K(rho,z) = INT_{-D/2}^{D/2} INT_{-pi}^{pi} exp(-jkR)/R  dphi dz'      (Burke eq.1)
!      R = sqrt(rho^2 + a^2 + (z-z')^2 - 2*a*rho*cos(phi))
!
!  RTWK (Burke eq. 3): evaluation points on-axis, current as a filament,
!      K0(rho,z) = 2*pi * INT e^{-jkR0}/R0 dz',  R0 = sqrt(rho^2+a^2+(z-z')^2)
!  This is exactly the "R -> sqrt(|dr|^2+a^2)" reduced-kernel offset used
!  below in source_gauss_nec, applied to every wire-wire pair (not just
!  self). That part of the original module was correct and is unchanged.
!
!  ETWK (Burke eq. 2, 4, 5): removes the singular 1/R term from a series
!  expansion of the exponential and integrates THAT term analytically over
!  z' (closed form, eq. 4/5), leaving only a well-behaved numerical
!  integral. Burke shows RTWK's self-term error is poor once Delta/a is
!  order 1 or less, and demonstrates NEC-5 current going unstable with
!  RTWK at small Delta/a (Fig. 2) while ETWK stays stable to very small
!  Delta/a (Fig. 3). That is precisely the segment-length/radius regime at
!  a bent junction with short segments -- which is why ETWK, not just the
!  RTWK offset, is the more targeted candidate for your NEAR-branch
!  investigation.
!
!  SCOPE / WHAT I DERIVED VS WHAT'S IN THE PAPER:
!   - Eq. 1-5 (RTWK, ETWK, the closed-form log-singularity extraction) are
!     Burke's, reproduced directly. Nothing in that derivation requires the
!     field point to be ON the source segment -- (rho,z) is just "field
!     point in cylindrical coordinates relative to a straight source
!     segment's axis," so the same closed form applies to a DIFFERENT
!     segment's field point too, with rho computed as the true perpendicular
!     distance from the test point to the source segment's axis line. This
!     is now applied to NEAR (node-sharing, different-segment) pairs in
!     source_pair_etwk below, not just self -- see that routine's header for
!     the projection geometry. This generalization (using it for NEAR pairs
!     at all, and using the geometric rho rather than a fixed rho=a/rho=0
!     convention there) is mine, built directly on Burke's eq. 1-5, not
!     something the paper states explicitly (his numerical results are all
!     self-term / far-pair convergence, not adjacent-segment near terms).
!   - Burke's eq. 2/4/5 derivation is for a CONSTANT source density (his
!     "typical integral ... due to constant source density"). Your rooftop
!     basis needs the same kernel WEIGHTED by a linear ramp scalar_q(z') =
!     z'/L or (L-z')/L, which Burke's closed form does not directly cover.
!     For the weighted (Ivec) piece I used standard singularity-subtraction:
!     evaluate the ramp weight at the SOURCE-segment coordinate nearest the
!     singularity (the axial projection of the test point, not the test
!     point's own position), and quadrature the smooth remainder as usual.
!     That is a reasonable, standard technique but it is MY extension, not
!     a formula from the paper -- flagged in etwk_core below.
!   - FAR pairs still use the plain RTWK offset (source_gauss_nec) -- no
!     rapid-variation concern there, the extra machinery isn't worth it.
!
!  Reference: G. J. Burke, "Accuracy of Reduced and Extended Thin-Wire
!  Kernels," LLNL-PROC-409033, ACES 2009.
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m, only: SEGMENT_TYPE
   use basis_builder_m

   implicit none; private

   public :: NEC_ZFILL_TYPE
   public :: KERNEL_RTWK, KERNEL_ETWK

   integer, parameter :: KERNEL_RTWK = 1
   integer, parameter :: KERNEL_ETWK = 2

   integer, parameter :: NQ_FAR  = 4
   integer, parameter :: NQ_NEAR = 16
   integer, parameter :: NQ_PHI  = 16    ! phi-integral quadrature for ETWK

   real, parameter :: XI4(4) = [ 0.069431844, 0.330009478, 0.669990522, 0.930568156 ]
   real, parameter :: W4(4)  = [ 0.173927423, 0.326072577, 0.326072577, 0.173927423 ]

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
   type :: NEC_ZFILL_TYPE
      integer :: selfKernel = KERNEL_ETWK   ! RTWK or ETWK for the self term
                                             ! (NEAR/FAR always use the RTWK
                                             ! offset -- see header note)
   contains
      procedure          :: fill_matrix_nec
      procedure, private :: Z_half_pair_nec
      procedure, private :: source_gauss_nec
      procedure, private :: source_self_rtwk
      procedure, private :: source_self_etwk
      procedure, private :: source_pair_etwk
      procedure, private :: etwk_core
   end type NEC_ZFILL_TYPE

contains

!==============================================================================
!  fill_matrix_nec: plain Galerkin, same structure as zfill_m::fill_matrix.
!  Upper triangle only; matrix is symmetric (Galerkin), same as zfill_m.
!==============================================================================
   subroutine fill_matrix_nec(this, Basis, Segs, Bk, zMat, zGroundRefl)

      class(NEC_ZFILL_TYPE), intent(inout)        :: this
      type(BASIS2_TYPE),     intent(in)           :: Basis(:)
      type(SEGMENT_TYPE),    intent(in)           :: Segs(:)
      real,                  intent(in)           :: Bk
      complex, allocatable,  intent(out)          :: zMat(:,:)
      complex, optional,     intent(in)           :: zGroundRefl

      integer :: nB, m, n, p, q
      complex :: Zmn, Refl
      logical :: hasGround

      nB = size(Basis)
      allocate(zMat(nB, nB))
      zMat = zZERO

      hasGround = present(zGroundRefl)
      Refl      = zZERO
      if (hasGround) Refl = zGroundRefl

      write(*,'(a,i6,a,i0)') '  fill_matrix_nec: filling ', nB, &
         'x'//trim(adjustl(itoa(nB)))//' Z matrix, selfKernel=', this%selfKernel

      do m = 1, nB
         do n = m, nB

            Zmn = zZERO

            do p = 1, 2
               do q = 1, 2
                  Zmn = Zmn + this%Z_half_pair_nec( &
                           Basis(m)%half(p), Basis(n)%half(q), &
                           Basis(m)%radius,  Segs, Bk,         &
                           useImage=.false., Refl=zZERO )
               end do
            end do

            if (hasGround .and. abs(Refl) > ZERO) then
               do p = 1, 2
                  do q = 1, 2
                     Zmn = Zmn + this%Z_half_pair_nec( &
                              Basis(m)%half(p), Basis(n)%half(q), &
                              Basis(m)%radius,  Segs, Bk,         &
                              useImage=.true.,  Refl=Refl )
                  end do
               end do
            end if

            zMat(m, n) = Zmn
            !zMat(n, m) = Zmn    ! Galerkin symmetry -- uncomment for full matrix

         end do
      end do

   end subroutine fill_matrix_nec


!==============================================================================
!  Z_half_pair_nec: one (test half, source half) contribution. Full Galerkin
!  test quadrature (nQtest points), same as zfill_m. Only the source-side
!  kernel differs: RTWK offset for NEAR/FAR (source_gauss_nec), selectable
!  RTWK/ETWK for SELF (source_self_rtwk / source_self_etwk).
!==============================================================================
   function Z_half_pair_nec(this, Hp, Hq, wireRadius, Segs, Bk, useImage, Refl) result(Z)

      class(NEC_ZFILL_TYPE), intent(inout) :: this
      type(HALF_TYPE),       intent(in)    :: Hp
      type(HALF_TYPE),       intent(in)    :: Hq
      real,                  intent(in)    :: wireRadius
      type(SEGMENT_TYPE),    intent(in)    :: Segs(:)
      real,                  intent(in)    :: Bk
      logical,                intent(in)    :: useImage
      complex,                intent(in)    :: Refl
      complex                              :: Z

      type(SEGMENT_TYPE) :: Sp, Sq
      logical  :: isSelf, isNear
      integer  :: ip, nQtest
      real     :: xTest, Lp, scalar_p, uDotu
      real     :: vTest(3)
      complex  :: Ivec, Iscl, A_pq, Phi_pq, jkEta, zSign

      Sp = Segs(Hp%iSeg)
      Sq = Segs(Hq%iSeg)

      isSelf = (Hp%iSeg == Hq%iSeg) .and. (.not. useImage)
      isNear = segments_share_node(Sp, Sq) .and. (.not. isSelf)

      jkEta = zIMAG * Bk * ETA0

      zSign = zONE
      if (useImage) zSign = Refl

      uDotu = dot_product(Sp%uHat, Sq%uHat)
      if (useImage) then
         uDotu = Sp%uHat(1)*Sq%uHat(1) &
               + Sp%uHat(2)*Sq%uHat(2) &
               - Sp%uHat(3)*Sq%uHat(3)
      end if

      Lp     = Sp%length
      nQtest = NQ_FAR
      if (isSelf .or. isNear) nQtest = NQ_NEAR

      A_pq   = zZERO
      Phi_pq = zZERO

      do ip = 1, nQtest

         xTest    = xi_n(ip, nQtest) * Lp
         vTest    = Sp%vNodes(:,1) + xTest * Sp%uHat
         scalar_p = scalar_fn(xTest, Lp, Hp%iEnd)

         if (isSelf) then
            if (this%selfKernel == KERNEL_ETWK) then
               call this%source_self_etwk(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            else
               call this%source_self_rtwk(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            end if
         else if (isNear .and. .not. useImage) then
            ! NEAR, different segments sharing a node: geometric-rho ETWK
            ! (see source_pair_etwk header). Image terms fall through to the
            ! plain RTWK path below -- the reflected geometry changes the
            ! projection algebra and I haven't worked that through yet.
            call this%source_pair_etwk(vTest, Sq, wireRadius, Bk, Hq%iEnd, Ivec, Iscl)
         else
            call this%source_gauss_nec(vTest, Sq, wireRadius, Bk, Hq%iEnd, isNear, useImage, Ivec, Iscl)
         end if

         A_pq   = A_pq   + w_n(ip, nQtest) * Lp * scalar_p * Ivec
         Phi_pq = Phi_pq + w_n(ip, nQtest) * Lp             * Iscl

      end do

      A_pq   = Hp%effSign * Hq%effSign * uDotu * A_pq
      Phi_pq = Hp%div     * Hq%div              * Phi_pq

      Z = zSign * jkEta * (A_pq - Phi_pq / (Bk * Bk))

   end function Z_half_pair_nec


!==============================================================================
!  source_gauss_nec: NEAR/FAR source integration with the RTWK reduced-kernel
!  radius offset applied universally (Burke eq. 3, R0 = sqrt(rho^2+a^2+dz^2),
!  which for a general 3-D pair reduces to R = sqrt(|dr|^2 + a^2) since
!  rho^2+dz^2 is exactly the squared distance from the test point to the
!  point on the source axis). Unchanged from the previous version; validated
!  against Burke's R0 definition.
!
!  ASSUMPTION FLAGGED (unchanged from before): uses `wireRadius` for both
!  test and source segment. If SEGMENT_TYPE carries a per-segment radius,
!  use Sq's own radius for the source-side offset instead.
!==============================================================================
   subroutine source_gauss_nec(this, vTest, Sq, wireRadius, Bk, iEnd_q, isNear, useImage, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: wireRadius
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      logical,                intent(in)  :: isNear
      logical,                intent(in)  :: useImage
      complex,                intent(out) :: Ivec, Iscl

      integer :: iq, nQsrc
      real    :: xSrc, Lq, R, Rsq, scalar_q
      real    :: vSrc(3), vSrcImg(3), vR(3)
      complex :: Green

      nQsrc = NQ_FAR
      if (isNear) nQsrc = NQ_NEAR

      Lq   = Sq%length
      Ivec = zZERO
      Iscl = zZERO

      do iq = 1, nQsrc

         xSrc = xi_n(iq, nQsrc) * Lq
         vSrc = Sq%vNodes(:,1) + xSrc * Sq%uHat

         if (useImage) then
            vSrcImg    = vSrc
            vSrcImg(3) = -vSrc(3)
            vR = vTest - vSrcImg
         else
            vR = vTest - vSrc
         end if

         Rsq = dot_product(vR, vR) + wireRadius * wireRadius   ! RTWK offset
         R   = sqrt(Rsq)
         if (R < 1.0e-12) R = 1.0e-12

         Green = w_n(iq, nQsrc) * Lq * exp(-zIMAG*Bk*R) / (FOURPI * R)

         scalar_q = scalar_fn(xSrc, Lq, iEnd_q)

         Ivec = Ivec + scalar_q * Green
         Iscl = Iscl +            Green

      end do

   end subroutine source_gauss_nec


!==============================================================================
!  source_self_rtwk: RTWK self term, Burke eq. 3, rho=0 (test on axis --
!  Burke: "K0 was evaluated at the center of the segment ... since this is
!  the way it is used"). This is algebraically the same reduced kernel as
!  zfill_m's Gibson formula; kept as a numerically-integrated (rather than
!  closed-form) version here so it shares the phi-free structure with
!  source_self_etwk below and the two are directly comparable.
!==============================================================================
   subroutine source_self_rtwk(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x, a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      integer :: iz
      real    :: zp, R0, scalar_q
      complex :: Green

      Ivec = zZERO
      Iscl = zZERO

      do iz = 1, NQ_NEAR
         zp = xi_n(iz, NQ_NEAR) * L                 ! z' in [0,L], x is test position
         R0 = sqrt(a*a + (x - zp)*(x - zp))
         if (R0 < 1.0e-12) R0 = 1.0e-12

         Green    = w_n(iz, NQ_NEAR) * L * exp(-zIMAG*Bk*R0) / (FOURPI * R0)
         scalar_q = scalar_fn(zp, L, iEnd_q)

         Ivec = Ivec + scalar_q * Green
         Iscl = Iscl +            Green
      end do

   end subroutine source_self_rtwk


!==============================================================================
!  source_self_etwk: ETWK self term, Burke eq. 2, 4, 5, evaluated at the wire
!  SURFACE (rho=a), matching Burke's own ETWK self-term convention ("The
!  ETWK was evaluated at the wire surface, K1(a,0)").
!
!  K1(rho,z) = 2*pi * INT_{-L/2}^{L/2} (e^{-jkR0}-1)/R0 dz'      [regular]
!            + INT_{-pi}^{pi} Kz(rho,z,phi) dphi                 [singular, closed-form-in-z']
!
!  where (eq. 5, singularity extracted):
!    Kz(rho,z,phi) = -log(a^2+rho^2-2*a*rho*cos(phi))
!                   + log[ (-z1+sqrt(a^2+z1^2+rho^2-2*a*rho*cos(phi)))
!                        * ( z2+sqrt(a^2+z2^2+rho^2-2*a*rho*cos(phi))) ]
!    z1 = -L/2 - z,  z2 = L/2 - z    (z measured from segment center)
!
!  and the singular piece integrates in closed form:
!    INT_{-pi}^{pi} log(a^2+rho^2-2*a*rho*cos(phi)) dphi = 4*pi*log(max(a,rho))
!
!  Both formulas are Burke's, reproduced directly (relabeled to this
!  module's x-from-left-node convention: z = x - L/2).
!
!  WEIGHTED (Ivec) EXTENSION -- NOT FROM THE PAPER:
!  Burke's K1 is for constant source density. For the rooftop scalar_q(z')
!  ramp, I apply standard singularity subtraction: the closed-form log
!  (singular) term is weighted by scalar_q evaluated AT THE TEST POINT
!  (since the z' dependence in that term has already been integrated out
!  analytically), while the regular (e^{-jkR0}-1)/R0 term is weighted
!  pointwise by scalar_q(z') under the z' quadrature, as usual. This is a
!  reasonable standard approximation, not a formula given in the paper --
!  flagging it explicitly so it isn't mistaken for Burke's result.
!==============================================================================
   subroutine source_self_etwk(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x       ! test position, 0..L from left node
      real,                   intent(in)  :: a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      ! Burke's ETWK self-term convention: evaluate at the wire surface
      ! (rho=a), not the axis -- see header note in etwk_core.
      call this%etwk_core(a, x, a, L, iEnd_q, Bk, Ivec, Iscl)

   end subroutine source_self_etwk


!==============================================================================
!  source_pair_etwk: ETWK applied to a NEAR (different-segment, node-sharing)
!  pair. Projects the test point onto the source segment Sq's axis line to
!  get the geometric (rho, s) that Burke's eq. 1-5 need -- this is the
!  generalization discussed in the module header: the closed-form
!  log-singularity extraction is valid for ANY straight source segment and
!  ANY field point, not just the self-term case.
!
!  Geometry: for source axis point at parameter s in [0,Lq] from Sq's left
!  node A, position = A + s*uHat. Let d0 = vTest - A. Then:
!    s_test = dot(d0, uHat)              -- projection of vTest onto the axis
!    dperp  = d0 - s_test*uHat           -- perpendicular component
!    rho    = |dperp|                    -- true perpendicular distance
!  and |vTest - (A+s*uHat)|^2 = rho^2 + (s_test-s)^2 for any s, which is
!  exactly Burke's R0(rho,z-z') form with z = s_test (measured from A).
!  s_test can legitimately fall outside [0,Lq] (test point projects beyond
!  the source segment's own extent) -- the closed form is valid there too.
!==============================================================================
   subroutine source_pair_etwk(this, vTest, Sq, wireRadius, Bk, iEnd_q, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: wireRadius   ! source wire radius, a
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      complex,                intent(out) :: Ivec, Iscl

      real :: d0(3), dperp(3), s_test, rho, Lq

      Lq = Sq%length
      d0 = vTest - Sq%vNodes(:,1)
      s_test = dot_product(d0, Sq%uHat)
      dperp  = d0 - s_test * Sq%uHat
      rho    = norm2(dperp)

      call this%etwk_core(rho, s_test, wireRadius, Lq, iEnd_q, Bk, Ivec, Iscl)

   end subroutine source_pair_etwk


!==============================================================================
!  etwk_core: shared ETWK math (Burke eq. 2, 4, 5), factored out of
!  source_self_etwk / source_pair_etwk. rho and x (field-point axial
!  coordinate, measured from the source segment's LEFT node, 0..L range but
!  not restricted to it) are supplied by the caller; everything else is the
!  same closed-form/quadrature split described in the module header.
!
!  WEIGHTED (Ivec) EXTENSION -- NOT FROM THE PAPER (see module header):
!  the closed-form singular term is weighted by scalar_q evaluated at x --
!  i.e. at the SOURCE segment's own coordinate nearest the field point's
!  axial projection, which is where the near-singular behavior is
!  concentrated. This is the same substitution used before, just now stated
!  generally: x plays the role "z1/z2 are built from" in both call sites.
!==============================================================================
   subroutine etwk_core(this, rho, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: rho     ! perpendicular distance, field pt to source axis
      real,                   intent(in)  :: x       ! field pt axial coord, 0..L from left node (source frame)
      real,                   intent(in)  :: a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      integer :: iz, iphi
      real    :: zp, z, z1, z2, R0, scalar_q, scalar_test
      real    :: phi, cphi, singPart, regPhiIntegrand, phiIntegral
      complex :: Green0, term1_vec, term1_scl

      z  = x - L/2.0          ! recenter to Burke's [-L/2, L/2] convention
      z1 = -L/2.0 - z
      z2 =  L/2.0 - z

      ! --- Regular term: 2*pi * INT (e^{-jkR0}-1)/R0 dz', both unweighted
      !     (Iscl) and ramp-weighted (Ivec). R0 per eq.2 = sqrt(rho^2+a^2+(z-z')^2)
      !     (R evaluated at phi=pi/2, per Burke's definition below eq.2).
      term1_vec = zZERO
      term1_scl = zZERO
      do iz = 1, NQ_NEAR
         zp = xi_n(iz, NQ_NEAR) * L                       ! [0,L] from left node
         R0 = sqrt(rho*rho + a*a + (x - zp)*(x - zp))
         if (R0 < 1.0e-12) R0 = 1.0e-12

         Green0   = w_n(iz, NQ_NEAR) * L * (exp(-zIMAG*Bk*R0) - ONE) / R0
         scalar_q = scalar_fn(zp, L, iEnd_q)

         term1_vec = term1_vec + scalar_q * Green0
         term1_scl = term1_scl +            Green0
      end do
      term1_vec = 2.0 * PI * term1_vec
      term1_scl = 2.0 * PI * term1_scl

      ! --- Singular term: INT_{-pi}^{pi} Kz(rho,z,phi) dphi via eq. 5,
      !     closed-form log-singularity extraction + Gauss-Legendre over phi
      singPart = 4.0 * PI * log(max(a, rho))

      phiIntegral = 0.0
      do iphi = 1, NQ_PHI
         phi  = -PI + 2.0*PI * xi_n(iphi, NQ_PHI)          ! map [0,1] -> [-pi,pi]
         cphi = cos(phi)

         regPhiIntegrand = log( &
              ( -z1 + sqrt(a*a + z1*z1 + rho*rho - 2.0*a*rho*cphi) ) * &
              (  z2 + sqrt(a*a + z2*z2 + rho*rho - 2.0*a*rho*cphi) ) )

         phiIntegral = phiIntegral + w_n(iphi, NQ_PHI) * 2.0*PI * regPhiIntegrand
      end do

      ! Iscl: unweighted K1/(4*pi), matching zfill_m's G=exp(-jkR)/(4*pi*R) convention
      ! NOTE: term1_scl is already complex (carries e^{-jkR0} phase from
      ! Green0) -- do NOT wrap in cmplx(...,0.0) here, that silently drops
      ! its imaginary part. (-singPart+phiIntegral) is real and promotes
      ! fine under ordinary complex+real addition.
      Iscl = (term1_scl + (-singPart + phiIntegral)) / FOURPI

      ! Ivec: singularity-subtraction weighting -- see header note above
      scalar_test = scalar_fn(x, L, iEnd_q)
      Ivec = (term1_vec + scalar_test * (-singPart + phiIntegral)) / FOURPI

   end subroutine etwk_core


!==============================================================================
!  Helpers
!==============================================================================

   pure real function scalar_fn(x, L, iEnd)
      real,    intent(in) :: x, L
      integer, intent(in) :: iEnd
      if (iEnd == 2) then
         scalar_fn = x / L
      else
         scalar_fn = (L - x) / L
      end if
   end function scalar_fn

   pure logical function segments_share_node(Sp, Sq)
      type(SEGMENT_TYPE), intent(in) :: Sp, Sq
      segments_share_node = &
         (Sp%iLeftNode  == Sq%iLeftNode)  .or. &
         (Sp%iLeftNode  == Sq%iRightNode) .or. &
         (Sp%iRightNode == Sq%iLeftNode)  .or. &
         (Sp%iRightNode == Sq%iRightNode)
   end function segments_share_node

   pure real function xi_n(i, nQ)
      integer, intent(in) :: i, nQ
      if (nQ == NQ_FAR) then
         xi_n = XI4(i)
      else
         xi_n = XI16(i)
      end if
   end function xi_n

   pure real function w_n(i, nQ)
      integer, intent(in) :: i, nQ
      if (nQ == NQ_FAR) then
         w_n = W4(i)
      else
         w_n = W16(i)
      end if
   end function w_n

   pure function itoa(n) result(s)
      integer, intent(in) :: n
      character(len=12) :: s
      write(s,'(i0)') n
      s = adjustl(s)
   end function itoa

end module zfill_nec_m
