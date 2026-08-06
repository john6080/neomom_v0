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
!  This is the "R -> sqrt(|dr|^2+a^2)" reduced-kernel offset used below in
!  source_gauss_nec. CORRECTION: this was originally applied to every
!  wire-wire pair unconditionally, including genuine FAR pairs. That was
!  wrong -- for closely-spaced parallel wires, softening 1/R on FAR
!  cross-wire pairs weakens mutual-coupling cancellation and inflates net
!  reactance (found via a shorted-parallel-wire-TL test case: Zin reactance
!  was ~293 ohm against zfill_m's ~171 ohm reference; scoping the offset to
!  isNear pairs only, matching original zfill_m's bare-R treatment of FAR
!  pairs, is what closed most of that gap -- see source_gauss_nec).
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
!  PLAIN-LANGUAGE SUMMARY (RTWK vs ETWK):
!
!  RTWK -- Reduced Thin-Wire Kernel. The older, simpler approximation.
!  Current is modeled as a filament on the wire's axis; the field is
!  evaluated with the wire radius folded in only as an offset under the
!  square root (R0 = sqrt(rho^2+a^2+(z-z')^2)) rather than a true singular
!  axis-to-axis distance. A single 1-D integral over the source segment,
!  cheap, and exactly what Gibson's closed-form self term (zfill_m) already
!  computes. Degrades once segment-length/radius (Delta/a) gets down around
!  1 or less -- e.g. a short segment near a bent junction, or a tightly-
!  spaced parallel wire.
!
!  ETWK -- Extended Thin-Wire Kernel. A more accurate treatment for that
!  same small-Delta/a regime. Starts from the exact kernel (current on the
!  actual cylindrical surface, integrated around the circumference AND
!  along the axis), splits it into a well-behaved remainder (numerical) and
!  the genuinely singular 1/R part (pulled out and integrated ANALYTICALLY
!  in closed form -- the log(...) expressions in etwk_core, Burke eq.4/5).
!  Stays numerically stable and accurate even as segments get very short
!  relative to the wire radius, exactly where RTWK becomes unreliable
!  (Burke's NEC-5 dipole current instability example, Fig.2 vs Fig.3).
!
!  HOW THIS MODULE ROUTES BETWEEN THEM:
!   - selfKernel = KERNEL_RTWK  -> Gibson's closed form (self term only).
!   - selfKernel = KERNEL_ETWK  -> Burke closed-form singularity extraction
!                                   (self term).
!   - isNearTouching pairs (shares a node, or axis gap within
!     C3_radMult*wireRadius) -> ALWAYS ETWK via source_pair_etwk,
!     regardless of selfKernel -- that flag only ever governs the self term.
!   - isNear-but-not-touching pairs (C1_lenMult or C2_lambda triggered) ->
!     RTWK-style plain quadrature at elevated (NQ_NEAR, 16-point) order,
!     NOT ETWK -- see the isNearTouching note at its assignment in
!     Z_half_pair_nec for why these were deliberately kept off the ETWK
!     path (empirically overcorrected: Zin reactance blew up to +74.7 ohm
!     before this split was added).
!   - True FAR pairs -> RTWK-style plain quadrature at 4-point (NQ_FAR)
!     order.
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
   public :: KERNEL_RTWK, KERNEL_ETWK, KERNEL_EXACT, KERNEL_BARE

   integer, parameter :: KERNEL_RTWK = 1
   integer, parameter :: KERNEL_ETWK = 2
   integer, parameter :: KERNEL_EXACT = 3   ! direct double (z',phi) quadrature
                                             ! of the true kernel -- see
                                             ! exact_core header. No closed-
                                             ! form approximation at all;
                                             ! added after validating that
                                             ! ETWK underestimates the true
                                             ! kernel by up to ~17% when
                                             ! rho~a (confirmed by brute-
                                             ! force comparison on the
                                             ! shorted-parallel-wire-TL test
                                             ! case's 90-degree junction).
   integer, parameter :: KERNEL_BARE = 4    ! bare R = |dr|, NO offset of any
                                             ! kind, ever -- exact match to
                                             ! original zfill_m::source_gauss
                                             ! (verified by direct inspection:
                                             ! it never adds a^2, for NEAR or
                                             ! FAR). NOTE: KERNEL_RTWK in this
                                             ! module's source_gauss_nec is
                                             ! NOT the same thing -- it adds
                                             ! a^2 whenever isNear is true.
                                             ! Added specifically as a true
                                             ! apples-to-apples baseline for
                                             ! nearKernel, since KERNEL_RTWK
                                             ! there turned out not to be one.

   integer, parameter :: NQ_FAR  = 4
   integer, parameter :: NQ_NEAR = 16
   integer, parameter :: NQ_PHI  = 16    ! phi-integral quadrature for ETWK
   integer, parameter :: NQ_EXACT = 32   ! double quadrature order for
                                          ! KERNEL_EXACT, both z' and phi.
                                          ! Validated: even NQ_EXACT=16
                                          ! matches a converged high-
                                          ! resolution trapezoid reference to
                                          ! 7 sig figs at the smallest rho
                                          ! tested (rho/a~0.13) -- the
                                          ! integrand is smooth (R>=a always,
                                          ! no true singularity), so this is
                                          ! generous headroom, not a
                                          ! minimum-required order.

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

   ! 32-point Gauss-Legendre on [0,1], generated directly (numpy
   ! leggauss) rather than hand-transcribed, for KERNEL_EXACT's double
   ! (z',phi) quadrature.
   real, parameter :: XI32(32) = [ &
      1.3680690753E-03, 7.1942442274E-03, 1.7618872206E-02, 3.2546962031E-02, &
      5.1839422117E-02, 7.5316193134E-02, 1.0275810202E-01, 1.3390894063E-01, &
      1.6847786653E-01, 2.0614212138E-01, 2.4655004553E-01, 2.8932436193E-01, &
      3.3406569886E-01, 3.8035631887E-01, 4.2776401921E-01, 4.7584616716E-01, &
      5.2415383284E-01, 5.7223598079E-01, 6.1964368113E-01, 6.6593430114E-01, &
      7.1067563807E-01, 7.5344995447E-01, 7.9385787862E-01, 8.3152213347E-01, &
      8.6609105937E-01, 8.9724189798E-01, 9.2468380687E-01, 9.4816057788E-01, &
      9.6745303797E-01, 9.8238112779E-01, 9.9280575577E-01, 9.9863193092E-01 ]

   real, parameter :: W32(32) = [ &
      3.5093050047E-03, 8.1371973655E-03, 1.2696032655E-02, 1.7136931457E-02, &
      2.1417949011E-02, 2.5499029631E-02, 2.9342046739E-02, 3.2911111388E-02, &
      3.6172897054E-02, 3.9096947894E-02, 4.1655962113E-02, 4.3826046502E-02, &
      4.5586939348E-02, 4.6922199540E-02, 4.7819360040E-02, 4.8270044257E-02, &
      4.8270044257E-02, 4.7819360040E-02, 4.6922199540E-02, 4.5586939348E-02, &
      4.3826046502E-02, 4.1655962113E-02, 3.9096947894E-02, 3.6172897054E-02, &
      3.2911111388E-02, 2.9342046739E-02, 2.5499029631E-02, 2.1417949011E-02, &
      1.7136931457E-02, 1.2696032655E-02, 8.1371973655E-03, 3.5093050047E-03 ]

!------------------------------------------------------------------------------
   type :: NEC_ZFILL_TYPE
      ! DEFAULTS (as of the shorted-parallel-wire-TL validation): set to
      ! reproduce original zfill_m exactly (RTWK self, BARE near-pairs,
      ! C1=C2=C3=0 -- i.e. NEAR classification reduces to pure node-sharing,
      ! same as original). Confirmed by direct test: this combination
      ! reproduced original zfill_m's Zin to full precision (171.05 ohm) on
      ! the shorted-TL case. The more elaborate options below (ETWK/EXACT
      ! self, EXACT/ETWK near-pairs, nonzero C1/C2/C3) are validated
      ! improvements ONLY for specific regimes tested so far (self term at
      ! extreme Delta/a; not yet confirmed for near-pairs in general) --
      ! they are NOT safe blanket defaults. Turn them on deliberately, one
      ! at a time, with an isolated A/B test against this baseline for
      ! whatever geometry you're applying them to -- the phi-averaged model
      ! (ETWK/EXACT) was found to make near-PAIR results substantially
      ! WORSE on the shorted-TL 90-degree-junction case despite being
      ! "more correct" kernel math in isolation, so "more accurate kernel"
      ! does not reliably imply "better Zin" once assembled into the full
      ! matrix -- there is no substitute for testing each change against a
      ! known-good reference on the actual geometry you care about.
     
     
   !  Baseline (selfKernel=RTWK, nearKernel=BARE, C1=C2=C3=0
     
  !   refined (selfKernel=EXACT, nearKernel=EXACT)

!Suggested runs, same matrix logic as before — worth running with 
!the file's current default settings first (validated baseline: 
!selfKernel=RTWK, nearKernel=BARE, C1=C2=C3=0), and separately
!with C3_radMult raised to something that actually captures the 3mm gap 
!(e.g. 5, the module's original default, since gap(3mm) < 5×a(5mm)) while
!leaving C1=C2=0 — that isolates C3_radMult alone, cleanly, for the first time this session.   
!
      integer :: selfKernel = KERNEL_RTWK    ! RTWK (=original zfill_m,
      !integer :: selfKernel = KERNEL_EXACT   ! RTWK (=original zfill_m,
                                              ! Gibson closed form) / ETWK /
                                              ! EXACT. ETWK/EXACT validated
                                              ! more accurate than RTWK
                                              ! specifically at extreme
                                              ! Delta/a (short-strap self
                                              ! terms) -- not yet tested
                                              ! against Gibson independently
                                              ! of RTWK at that regime; only
                                              ! RTWK has been directly
                                              ! confirmed to match Gibson.
      !integer :: nearKernel = KERNEL_EXACT    ! BARE (=original zfill_m) /
      integer :: nearKernel = KERNEL_BARE    ! BARE (=original zfill_m) /
                                              ! RTWK (bare + a^2 floor,
                                              ! NOT the same as original
                                              ! despite the name) / ETWK /
                                              ! EXACT (phi-averaged surface-
                                              ! current model). BARE is the
                                              ! only one confirmed to
                                              ! reproduce original zfill_m;
                                              ! the others substantially
                                              ! changed Zin on the shorted-
                                              ! TL case, direction and
                                              ! magnitude not yet understood
                                              ! well enough to recommend.

      ! Hybrid NEAR classification thresholds (see classify_near). Node-
      ! sharing is always NEAR regardless of these. DEFAULTS SET TO ZERO --
      ! i.e. NEAR reduces to pure node-sharing, matching original zfill_m --
      ! for the same reason as the kernel defaults above: nonzero values
      ! were never isolated from the nearKernel confound in this session's
      ! testing (every nonzero-C1/C2/C3 run also had a near-pair kernel
      ! choice active at the same time), so their real effect on Zin is
      ! still unknown. Re-enable deliberately, one at a time, with your own
      ! A/B test.
      
      !For every configuration actually tested and validated against a trustworthy 
      !reference this session, the original Gibson-formula zfill_m behavior is what
      !'s held up. The NEC5 module, as it stands, reproduces it exactly when set to
      !its now-default baseline (RTWK self, BARE near-pairs, C1=C2=C3=0) — which is really 
      !just a longer, more general reimplementation of the same physics, not a functional improvement.
      
      
      
      
      
      real :: C1_lenMult = 0.0    ! centroid sep < C1_lenMult * max(Lp,Lq)
      real :: C2_lambda  = 0.0    ! centroid sep < C2_lambda * lambda
      real :: C3_radMult = 0.0    ! axis-to-axis gap < C3_radMult * wireRadius
   contains
      procedure          :: fill_matrix_nec
      procedure, private :: Z_half_pair_nec
      procedure, private :: source_gauss_nec
      procedure, private :: source_gauss_bare
      procedure, private :: source_self_rtwk
      procedure, private :: source_self_etwk
      procedure, private :: source_pair_etwk
      procedure, private :: source_self_exact
      procedure, private :: source_pair_exact
      procedure, private :: etwk_core
      procedure, private :: exact_core
      procedure, private :: classify_near
      procedure, private :: gap_within_radius
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
      logical  :: isSelf, isNear, isNearTouching
      integer  :: ip, nQtest
      real     :: xTest, Lp, scalar_p, uDotu
      real     :: vTest(3)
      complex  :: Ivec, Iscl, A_pq, Phi_pq, jkEta, zSign

      Sp = Segs(Hp%iSeg)
      Sq = Segs(Hq%iSeg)

      isSelf = (Hp%iSeg == Hq%iSeg) .and. (.not. useImage)
      isNear = this%classify_near(Sp, Sq, wireRadius, Bk) .and. (.not. isSelf)

      ! Of the NEAR pairs, only route to the ETWK closed-form treatment
      ! (source_pair_etwk) when the field point's axial projection is
      ! actually likely to land at/near the source segment's own span --
      ! node-sharing or true surface proximity. The C1_lenMult/C2_lambda
      ! criteria in classify_near catch moderately-close, often collinear,
      ! non-touching pairs where the projection frequently falls WELL
      ! outside [0,L]; applying the singularity-subtracted ETWK formula
      ! there was overcorrecting (confirmed empirically: Zin reactance
      ! blew up to +74.7 ohm once those pairs started routing through it).
      ! Those pairs still get elevated (NQ_NEAR) quadrature order via
      ! isNear below -- that addresses the legitimate phase/quadrature-
      ! resolution concern C1/C2 were meant for -- just via plain RTWK
      ! quadrature (source_gauss_nec) rather than the closed-form ETWK path.
      isNearTouching = (segments_share_node(Sp, Sq) .or. &
                         this%gap_within_radius(Sp, Sq, wireRadius)) .and. (.not. isSelf)

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
            select case (this%selfKernel)
            case (KERNEL_EXACT)
               call this%source_self_exact(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            case (KERNEL_ETWK)
               call this%source_self_etwk(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            case default
               call this%source_self_rtwk(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            end select
         else if (isNearTouching .and. .not. useImage) then
            ! Node-sharing or true surface proximity. Default kernel here is
            ! configurable via nearKernel:
            !  KERNEL_EXACT/KERNEL_ETWK -> phi-averaged surface-current
            !    model (source_pair_exact/etwk), generalizing Burke's
            !    SELF-term formula to pair interactions -- Burke never
            !    validates this for pairs, only self. Testing hypothesis.
            !  KERNEL_RTWK -> simple filament + a^2-floor treatment, NO
            !    phi-averaging (source_gauss_nec, forced to near-quadrature
            !    order) -- matches original zfill_m's near-pair convention
            !    (bare R, or R with a^2 floor once isNear is true). Added
            !    as an option after EXACT vs ETWK barely moved Zin on the
            !    shorted-TL test, suggesting the phi-averaged model itself,
            !    not its accuracy, may be the wrong generalization for
            !    PAIR (non-self, different-segment) interactions.
            ! Image terms fall through to the plain RTWK path below -- the
            ! reflected geometry changes the projection algebra and I
            ! haven't worked that through yet.
            select case (this%nearKernel)
            case (KERNEL_EXACT)
               call this%source_pair_exact(vTest, Sq, wireRadius, Bk, Hq%iEnd, Ivec, Iscl)
            case (KERNEL_ETWK)
               call this%source_pair_etwk(vTest, Sq, wireRadius, Bk, Hq%iEnd, Ivec, Iscl)
            case (KERNEL_RTWK)
               call this%source_gauss_nec(vTest, Sq, wireRadius, Bk, Hq%iEnd, .true., useImage, Ivec, Iscl)
            case default   ! KERNEL_BARE
               call this%source_gauss_bare(vTest, Sq, Bk, Hq%iEnd, Ivec, Iscl)
            end select
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
!  source_gauss_nec: NEAR/FAR source integration. RTWK reduced-kernel radius
!  offset (Burke eq. 3, R0 = sqrt(rho^2+a^2+dz^2), which for a general 3-D
!  pair reduces to R = sqrt(|dr|^2 + a^2) since rho^2+dz^2 is exactly the
!  squared distance from the test point to the source axis) is applied ONLY
!  for isNear pairs -- see the FIX note at the Rsq computation below for why
!  applying it unconditionally (the original version of this routine) was
!  wrong. Genuine FAR pairs use bare R = |dr|, matching original zfill_m.
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

         ! RTWK offset (Burke eq.3's a^2 term) applied ONLY for isNear pairs,
         ! not unconditionally. FIX: this used to add wireRadius^2 to every
         ! pair including genuine FAR ones. For two closely-spaced parallel
         ! wires, input reactance is governed by the self-inductance MINUS
         ! mutual-inductance cancellation between the wires; softening 1/R
         ! (via +a^2) on cross-wire FAR-classified pairs weakens that mutual
         ! coupling and inflates net reactance -- confirmed empirically on
         ! the shorted-TL test case (Zin reactance dropped from ~293 toward
         ! zfill_m's ~171 ohm reference once this was scoped to isNear only).
         ! Genuine FAR pairs now match original zfill_m's bare-R treatment;
         ! the offset still applies for isNear (quadrature-resolution
         ! concern, where it's actually earning its keep).
         if (isNear) then
            Rsq = dot_product(vR, vR) + wireRadius * wireRadius
         else
            Rsq = dot_product(vR, vR)
         end if
         R   = sqrt(Rsq)
         if (R < 1.0e-12) R = 1.0e-12

         Green = w_n(iq, nQsrc) * Lq * exp(-zIMAG*Bk*R) / (FOURPI * R)

         scalar_q = scalar_fn(xSrc, Lq, iEnd_q)

         Ivec = Ivec + scalar_q * Green
         Iscl = Iscl +            Green

      end do

   end subroutine source_gauss_nec


!==============================================================================
!  source_gauss_bare: exact transcription of original zfill_m::source_gauss
!  (verified by direct inspection of the uploaded file). Bare R = |dr|, NO
!  offset of any kind -- not a^2, not phi-averaging. NQ_NEAR quadrature
!  order always (caller only invokes this when isNearTouching). This is the
!  true apples-to-apples baseline for isolating whether the kernel-formula
!  choice for near-touching pairs is what's driving the shorted-TL Zin
!  discrepancy, or whether it's something else entirely -- if this ALSO
!  lands near 270-295 ohm rather than zfill_m's 171, the bug is not in the
!  kernel formula at all.
!==============================================================================
   subroutine source_gauss_bare(this, vTest, Sq, Bk, iEnd_q, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      complex,                intent(out) :: Ivec, Iscl

      integer :: iq
      real    :: xSrc, Lq, R, scalar_q
      real    :: vSrc(3), vR(3)
      complex :: Green

      Lq   = Sq%length
      Ivec = zZERO
      Iscl = zZERO

      do iq = 1, NQ_NEAR

         xSrc = xi_n(iq, NQ_NEAR) * Lq
         vSrc = Sq%vNodes(:,1) + xSrc * Sq%uHat

         vR = vTest - vSrc
         R  = norm2(vR)
         if (R < 1.0e-12) R = 1.0e-12

         Green = w_n(iq, NQ_NEAR) * Lq * exp(-zIMAG*Bk*R) / (FOURPI * R)

         scalar_q = scalar_fn(xSrc, Lq, iEnd_q)

         Ivec = Ivec + scalar_q * Green
         Iscl = Iscl +            Green

      end do

   end subroutine source_gauss_bare


!==============================================================================
!  source_self_rtwk: RTWK self term.
!
!  FIX: this previously did a fixed 16-point Gauss-Legendre quadrature of
!  e^{-jkR0}/R0 directly over the whole segment. For a=x << L (typical thin
!  wire, L/a often in the hundreds), 1/R0 is a ridge only about `a` wide
!  sitting inside a domain of length L -- a global 16-point rule essentially
!  never resolves it. That produced Zin = 68.97 - j134.04 on a resonant
!  half-wave dipole, against the correct ~73+j7 (Gibson closed form) and
!  ~73+j7 (ETWK) -- not a sign ETWK was wrong, a sign this quadrature
!  approximation was much too crude for a legitimate comparison.
!
!  This is mathematically the SAME integral zfill_m's Gibson closed form
!  evaluates (R0 = sqrt(a^2+x^2) is exactly Burke's RTWK R0 at rho=0), so
!  rather than fix the quadrature (which would just mean adding a
!  singularity-subtraction scheme identical in spirit to ETWK, at which
!  point it's not really a distinct "RTWK" baseline anymore), this now
!  calls Gibson's closed form directly. It exists here mainly so
!  selfKernel=KERNEL_RTWK gives a fast, exact reference to diff ETWK
!  against, not as an independent numerical method.
!
!  Reference: Gibson, "The Method of Moments in Electromagnetics", 2nd ed.,
!  Sec. 4.5.2, Eqs. 4.83-4.86 -- reproduced from zfill_m::source_self_analytical.
!==============================================================================
   subroutine source_self_rtwk(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x, a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      real    :: R0, RL, arglog
      complex :: S1_asc, S1_desc, S2

      R0     = sqrt(a*a + x*x)
      RL     = sqrt(a*a + (x - L)*(x - L))

      arglog = log( (x + R0) / max(abs(x - L + RL), 1.0e-30) )

      S1_asc  =  (RL/L - R0/L + (x/L)*arglog) - zIMAG*(Bk*L/2.0)   ! iEnd_q=2
      S1_desc = -(RL/L - R0/L + (x/L)*arglog) - zIMAG*(Bk*L/2.0) + arglog  ! iEnd_q=1

      S2 = (ONE/L) * (arglog - zIMAG*(Bk*L))

      S1_asc  = S1_asc  / FOURPI
      S1_desc = S1_desc / FOURPI
      S2      = S2 * L  / FOURPI

      Ivec = merge(S1_asc, S1_desc, iEnd_q == 2)
      Iscl = S2

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
      real    :: phi, cphi, singPart, regPhiIntegrand, phiIntegral, epsPhi
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

         ! eps = a^2+rho^2-2*a*rho*cos(phi) >= 0 always. The two factors
         ! below are (-z1)+sqrt(z1^2+eps) and z2+sqrt(z2^2+eps) -- each is
         ! mathematically >=0, but computed as X+sqrt(X^2+eps) this suffers
         ! catastrophic cancellation whenever X<0 and |X| is large relative
         ! to eps (i.e. the field-point axial projection lands well outside
         ! [0,L] -- expected now that classify_near can flag pairs close by
         ! distance but far apart along the axis). Use stable_xpsqrt below
         ! rather than the direct sum.
         epsPhi = a*a + rho*rho - 2.0*a*rho*cphi

         regPhiIntegrand = log( max( stable_xpsqrt(-z1, epsPhi) * stable_xpsqrt(z2, epsPhi), 1.0e-30 ) )

         phiIntegral = phiIntegral + w_n(iphi, NQ_PHI) * 2.0*PI * regPhiIntegrand
      end do

      ! Iscl: K1 normalized to match zfill_m's G=exp(-jkR)/(4*pi*R) filament
      ! convention (see derivation below -- final divisor is 8*pi^2, not 4*pi).
      ! NOTE: term1_scl is already complex (carries e^{-jkR0} phase from
      ! Green0) -- do NOT wrap in cmplx(...,0.0) here, that silently drops
      ! its imaginary part. (-singPart+phiIntegral) is real and promotes
      ! fine under ordinary complex+real addition.
      !
      ! NORMALIZATION (found by cross-checking against source_self_rtwk):
      ! Burke's K0 (eq.3) = 2*pi * INT e^{-jkR0}/R0 dz'. source_self_rtwk
      ! computes the plain filament integral INT e^{-jkR0}/R0 dz' directly
      ! (no 2*pi), normalized by /(4*pi) -- i.e. it computes K0/(8*pi^2).
      ! K1 is built on the SAME "K" convention as K0 (both approximate the
      ! same Burke eq.1 double integral), so it needs the SAME divisor,
      ! K1/(8*pi^2), not K1/(4*pi) -- the /(4*pi) alone is missing a
      ! factor of 2*pi, inflating every self/near-pair ETWK contribution.
      Iscl = (term1_scl + (-singPart + phiIntegral)) / (FOURPI * 2.0*PI)

      ! Ivec: singularity-subtraction weighting -- see header note above.
      ! Same /(8*pi^2) normalization fix as Iscl above -- both pieces of K1
      ! (term1_vec and the closed-form part) are on Burke's K-convention.
      scalar_test = scalar_fn(x, L, iEnd_q)
      Ivec = (term1_vec + scalar_test * (-singPart + phiIntegral)) / (FOURPI * 2.0*PI)

   end subroutine etwk_core


!==============================================================================
!  source_self_exact / source_pair_exact / exact_core: KERNEL_EXACT path.
!
!  No closed form, no approximation of any kind -- direct double Gauss-
!  Legendre quadrature (NQ_EXACT x NQ_EXACT = 32x32) of the true kernel
!
!      exp(-jkR)/R,   R = sqrt(rho^2 + a^2 + (x-z')^2 - 2*a*rho*cos(phi))
!
!  (Burke eq.1's integrand, before any RTWK/ETWK approximation is applied to
!  it). This exists because ETWK was validated (brute-force comparison
!  against a converged high-resolution trapezoid reference, on the
!  90-degree-junction shorted-parallel-wire-TL test case) to underestimate
!  the true kernel by up to ~17% specifically when rho is comparable to a --
!  ETWK's "regular" term approximates the true kernel's phi-dependence by
!  evaluating it once at phi=pi/2 and multiplying by 2*pi, which is a poor
!  approximation exactly in that regime. R is never actually zero here (it's
!  bounded below by a), so the integrand is smooth, not singular -- ordinary
!  Gauss-Legendre converges fast on it (verified: even NQ_EXACT=16 matched
!  the reference to 7 significant figures at the smallest rho tested,
!  rho/a~0.13; NQ_EXACT=32 here is generous headroom, not a bare minimum).
!  The ramp weight scalar_q(z') is applied directly inside the z' quadrature
!  -- no singularity-subtraction approximation needed at all for the
!  weighted (Ivec) term, unlike etwk_core.
!
!  Normalization: same /(8*pi^2) divisor as etwk_core, established by
!  cross-checking against source_self_rtwk (see etwk_core's Iscl comment for
!  the derivation) -- RTWK, ETWK, and EXACT all approximate (EXACT: exactly
!  equal, to quadrature precision) the same underlying Burke eq.1 double
!  integral, so all three need the same overall normalization to be
!  comparable / substitutable in Z_half_pair_nec.
!==============================================================================
   subroutine source_self_exact(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)
      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x, a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      ! Self term evaluated at the wire surface (rho=a), same convention as
      ! source_self_etwk / Burke's own ETWK self-term choice.
      call this%exact_core(a, x, a, L, iEnd_q, Bk, Ivec, Iscl)
   end subroutine source_self_exact


   subroutine source_pair_exact(this, vTest, Sq, wireRadius, Bk, iEnd_q, Ivec, Iscl)
      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: wireRadius
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      complex,                intent(out) :: Ivec, Iscl

      real :: d0(3), dperp(3), s_test, rho, Lq

      ! Same projection geometry as source_pair_etwk.
      Lq = Sq%length
      d0 = vTest - Sq%vNodes(:,1)
      s_test = dot_product(d0, Sq%uHat)
      dperp  = d0 - s_test * Sq%uHat
      rho    = norm2(dperp)

      call this%exact_core(rho, s_test, wireRadius, Lq, iEnd_q, Bk, Ivec, Iscl)
   end subroutine source_pair_exact


   subroutine exact_core(this, rho, x, a, L, iEnd_q, Bk, Ivec, Iscl)
      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: rho     ! perpendicular distance, field pt to source axis
      real,                   intent(in)  :: x       ! field pt axial coord, 0..L from left node (source frame)
      real,                   intent(in)  :: a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      integer :: iz, iphi
      real    :: zp, phi, cphi, R, scalar_q, wz
      complex :: kernel, sumScl, sumVec

      sumScl = zZERO
      sumVec = zZERO

      do iz = 1, NQ_EXACT
         zp = xi_n(iz, NQ_EXACT) * L                       ! [0,L] from left node
         wz = w_n(iz, NQ_EXACT) * L
         scalar_q = scalar_fn(zp, L, iEnd_q)

         do iphi = 1, NQ_EXACT
            phi  = -PI + 2.0*PI * xi_n(iphi, NQ_EXACT)
            cphi = cos(phi)

            R = sqrt(rho*rho + a*a + (x-zp)*(x-zp) - 2.0*a*rho*cphi)
            if (R < 1.0e-12) R = 1.0e-12   ! guard only; R>=a-rho... never
                                           ! actually reached in practice

            kernel = wz * w_n(iphi, NQ_EXACT)*2.0*PI * exp(-zIMAG*Bk*R) / R

            sumScl = sumScl +            kernel
            sumVec = sumVec + scalar_q * kernel
         end do
      end do

      Iscl = sumScl / (FOURPI * 2.0*PI)
      Ivec = sumVec / (FOURPI * 2.0*PI)

   end subroutine exact_core


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

!==============================================================================
!  classify_near: hybrid NEAR classification.
!
!  The original criterion (segments_share_node) only catches pairs
!  GUARANTEED to touch. It misses two other cases where the kernel needs
!  the same careful treatment:
!   - Non-touching segments whose CENTROIDS are close relative to their own
!     length (quadrature-resolution concern: 1/R varies fast relative to
!     the domain a fixed-order Gauss rule has to cover) or relative to
!     wavelength (phase-sampling concern: e^{-jkR} varies fast over the
!     quadrature domain).
!   - Segments whose AXES pass close together without touching at all --
!     e.g. a tightly-spaced parallel-wire transmission line. This is
!     governed by gap relative to wire radius (a), NOT segment length or
!     wavelength; Burke's Fig. 5 (parallel-wire Z0 vs s/d) is exactly this
!     regime and is why ETWK exists.
!
!  A pair is NEAR if it shares a node, OR centroid separation is within
!  C1_lenMult*max(Lp,Lq), OR within C2_lambda*lambda, OR the minimum
!  distance between the two AXIS SEGMENTS (finite segments, not infinite
!  lines -- see seg_seg_distance) is within C3_radMult*wireRadius.
!
!  ASSUMPTION FLAGGED: uses `wireRadius` (single value, same one passed
!  everywhere else in this module) for the C3 gap check. If your mesh mixes
!  wire gauges on a close-spaced pair, this won't distinguish them -- same
!  simplification already flagged in source_gauss_nec/source_pair_etwk.
!
!  Segment endpoints are computed as vNodes(:,1) + length*uHat rather than
!  assuming a second vNodes column exists -- matches how the rest of this
!  module (and zfill_m) reaches a segment's far end.
!==============================================================================
   pure logical function classify_near(this, Sp, Sq, wireRadius, Bk)
      class(NEC_ZFILL_TYPE), intent(in) :: this
      type(SEGMENT_TYPE),    intent(in) :: Sp, Sq
      real,                   intent(in) :: wireRadius
      real,                   intent(in) :: Bk

      real :: centP(3), centQ(3), dCent, Lmax, lambda

      if (segments_share_node(Sp, Sq)) then
         classify_near = .true.
         return
      end if

      centP = Sp%vNodes(:,1) + 0.5*Sp%length*Sp%uHat
      centQ = Sq%vNodes(:,1) + 0.5*Sq%length*Sq%uHat
      dCent = norm2(centP - centQ)
      Lmax  = max(Sp%length, Sq%length)
      lambda = 2.0*PI / max(Bk, 1.0e-30)

      if (dCent < this%C1_lenMult*Lmax) then
         classify_near = .true.
         return
      end if

      if (dCent < this%C2_lambda*lambda) then
         classify_near = .true.
         return
      end if

      classify_near = this%gap_within_radius(Sp, Sq, wireRadius)

   end function classify_near


!==============================================================================
!  gap_within_radius: true surface-proximity check only (axis-to-axis
!  segment distance vs. C3_radMult*wireRadius). Factored out of
!  classify_near so Z_half_pair_nec can use it directly to decide ETWK
!  routing (isNearTouching) without the broader C1/C2 distance criteria --
!  see the note at the isNearTouching assignment for why those two are
!  kept separate from the ETWK-routing decision.
!==============================================================================
   pure logical function gap_within_radius(this, Sp, Sq, wireRadius)
      class(NEC_ZFILL_TYPE), intent(in) :: this
      type(SEGMENT_TYPE),    intent(in) :: Sp, Sq
      real,                   intent(in) :: wireRadius

      real :: P1(3), Q1(3), P2(3), Q2(3), dAxis

      P1 = Sp%vNodes(:,1)
      Q1 = Sp%vNodes(:,1) + Sp%length*Sp%uHat
      P2 = Sq%vNodes(:,1)
      Q2 = Sq%vNodes(:,1) + Sq%length*Sq%uHat
      dAxis = seg_seg_distance(P1, Q1, P2, Q2)

      gap_within_radius = (dAxis < this%C3_radMult*wireRadius)

   end function gap_within_radius


!==============================================================================
!  seg_seg_distance: minimum distance between two finite 3-D line segments
!  (P1-Q1 and P2-Q2). Standard closest-point-between-segments algorithm
!  (e.g. Ericson, "Real-Time Collision Detection", sec. 5.1.9), NOT the
!  infinite-line distance -- using the infinite line would understate the
!  gap for segments that pass near each other's extended axis without
!  actually being close (e.g. two collinear, non-overlapping segments at
!  the far ends of a transmission line).
!==============================================================================
   pure real function seg_seg_distance(P1, Q1, P2, Q2)
      real, intent(in) :: P1(3), Q1(3), P2(3), Q2(3)

      real, parameter :: EPS = 1.0e-12
      real :: d1(3), d2(3), r(3), a, e, f, c, b, denom, s, t
      real :: c1(3), c2(3)

      d1 = Q1 - P1
      d2 = Q2 - P2
      r  = P1 - P2
      a  = dot_product(d1, d1)
      e  = dot_product(d2, d2)
      f  = dot_product(d2, r)

      if (a <= EPS .and. e <= EPS) then
         seg_seg_distance = norm2(r)
         return
      end if

      if (a <= EPS) then
         s = 0.0
         t = clamp01(f / e)
      else
         c = dot_product(d1, r)
         if (e <= EPS) then
            t = 0.0
            s = clamp01(-c / a)
         else
            b = dot_product(d1, d2)
            denom = a*e - b*b
            if (abs(denom) > EPS) then
               s = clamp01((b*f - c*e) / denom)
            else
               s = 0.0
            end if
            t = (b*s + f) / e
            if (t < 0.0) then
               t = 0.0
               s = clamp01(-c / a)
            else if (t > 1.0) then
               t = 1.0
               s = clamp01((b - c) / a)
            end if
         end if
      end if

      c1 = P1 + d1*s
      c2 = P2 + d2*t
      seg_seg_distance = norm2(c1 - c2)

   end function seg_seg_distance

   pure real function clamp01(v)
      real, intent(in) :: v
      clamp01 = max(0.0, min(1.0, v))
   end function clamp01

!==============================================================================
!  stable_xpsqrt: numerically stable X + sqrt(X^2+eps), eps>=0.
!  Mathematically always >=0 (sqrt(X^2+eps) >= |X|). Direct evaluation
!  suffers catastrophic cancellation when X<0 and |X| >> sqrt(eps) -- use
!  the conjugate form eps/(sqrt(X^2+eps)-X) there instead, whose
!  denominator is a sum of two non-negative terms (sqrt(...) and -X, both
!  >=0 when X<0) and so is well-conditioned.
!==============================================================================
   pure real function stable_xpsqrt(X, eps)
      real, intent(in) :: X, eps
      real :: s
      s = sqrt(X*X + eps)
      if (X >= 0.0) then
         stable_xpsqrt = X + s
      else
         stable_xpsqrt = eps / (s - X)
      end if
   end function stable_xpsqrt

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
      ! Explicit dispatch on nQ (was "if NQ_FAR else assume 16" -- silently
      ! wrong once a third table (32-pt, for KERNEL_EXACT) existed).
      select case (nQ)
      case (NQ_FAR)
         xi_n = XI4(i)
      case (NQ_NEAR)   ! == NQ_PHI (both 16) by construction
         xi_n = XI16(i)
      case (NQ_EXACT)
         xi_n = XI32(i)
      case default
         xi_n = XI16(i)   ! should not happen; fall back rather than crash
      end select
   end function xi_n

   pure real function w_n(i, nQ)
      integer, intent(in) :: i, nQ
      select case (nQ)
      case (NQ_FAR)
         w_n = W4(i)
      case (NQ_NEAR)
         w_n = W16(i)
      case (NQ_EXACT)
         w_n = W32(i)
      case default
         w_n = W16(i)
      end select
   end function w_n

   pure function itoa(n) result(s)
      integer, intent(in) :: n
      character(len=12) :: s
      write(s,'(i0)') n
      s = adjustl(s)
   end function itoa

end module zfill_nec_m
