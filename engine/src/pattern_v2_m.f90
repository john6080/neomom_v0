module pattern_v2_m

!==============================================================================
!  pattern_v2_m — far-field radiation pattern (BASIS2_TYPE, analytical integral)
!
!  Purpose:
!   Compute the complex far-field vector Er(nAng, 2) for a wire MOM solution.
!   Called by pattern_3d_m::pattern_3d as the sole pattern kernel.
!
!  Status:
!   Active production module.  Supersedes mesh_m::pattern_jfs_v2, which used
!   the centroid approximation (phase at vCtr, average shape value Favg=0.5).
!   This module uses an exact analytical integral for improved accuracy at
!   electrically large segments and large observation angles.
!
!==============================================================================
!  RELATION TO pattern_jfs_v2 (mesh_m)
!==============================================================================
!
!  Both compute the same physical quantity; the difference is the radiation
!  integral:
!
!  pattern_jfs_v2 (centroid, approximate):
!   vRad = uHat * L * cur(m) * Favg * exp(+j*vkout·vCtr) / (4π)
!   Favg = 0.5  (average of shape function over [0,L])
!   Phase reference: segment centroid vCtr
!   Error: O(k*L) in the phase, O((k*L)²) in amplitude; acceptable for L ≪ λ
!
!  pattern_v2 (left-node, analytical):
!   Phase ref at left node vL = Nodes(S%iLeftNode)%v
!   I_int = L * ∫₀¹ f(t) * exp(j*u*t) dt   (exact closed form)
!   u = dot(vkout, uHat) * L
!   Error: only floating-point roundoff; exact for any k*L
!
!  Use pattern_v2 for all new work.  pattern_jfs_v2 is retained in mesh_m
!  only for algorithmic reference.
!
!==============================================================================
!  RADIATION INTEGRAL — DERIVATION
!==============================================================================
!
!  For half h of basis function m, with:
!   vL    = left-node position   Nodes(S%iLeftNode)%v  [m]
!   uHat  = segment unit vector  (iLeftNode → iRightNode)
!   L     = segment length  [m]
!   t     = x/L ∈ [0,1]    (normalised position along segment)
!   iEnd  = 1 (descending f=1-t) or 2 (ascending f=t)
!   effS  = effSign ∈ {±1}
!
!  Outward propagation vector:
!   vkout = -AngleCut%vK(:,iAng) * bk    [rad/m, points away from origin]
!   (vK points toward origin, so negation gives outward direction)
!
!  Phase variables:
!   phi0 = dot(vkout, vL)          [rad, phase accumulated to left node]
!   u    = dot(vkout, uHat) * L    [rad, additional phase across segment]
!
!  Full contribution from this half to E:
!
!   dEr = -(j*k*ETA0/4π) * effS * cur(m) * exp(j*phi0)
!           * I_int * dot(uHat, uPol)
!
!  where I_int = L * ∫₀¹ f(t) * exp(j*u*t) dt.
!
!  Closed-form integrals:
!
!   iEnd=2 (f = t):
!     ∫₀¹ t * exp(jut) dt = exp(ju)/(ju) − (exp(ju)−1)/(ju)²
!     I_int = L * [ eju/ju − (eju−1)/ju² ]
!
!   iEnd=1 (f = 1−t):
!     ∫₀¹ (1−t) * exp(jut) dt = −1/(ju) + (exp(ju)−1)/(ju)²
!     I_int = L * [ −1/ju + (eju−1)/ju² ]
!
!  Taylor expansions for |u| < UTINY (avoids 0/0 when rhat ⊥ uHat or L→0):
!
!   iEnd=2: I_int/L = 1/2 + j*u/3  − u²/8   − j*u³/30   + O(u⁴)
!   iEnd=1: I_int/L = 1/2 + j*u/6  − u²/24  − j*u³/120  + O(u⁴)
!
!   Derived from Σₙ (ju)ⁿ/n! * ∫₀¹ tⁿ*f(t) dt:
!     iEnd=2: ∫₀¹ tⁿ⁺¹ dt = 1/(n+2)
!     iEnd=1: ∫₀¹ (1−t)tⁿ dt = 1/((n+1)(n+2))
!
!  Prefactor:
!   prefac = −j*k*ETA0/(4π)
!   ETA0 ≈ 376.7303 Ω (exact; note ETA0/4π ≈ 29.98 Ω ≈ 30 Ω)
!
!==============================================================================
!  GROUND PLANE IMAGE THEORY
!==============================================================================
!
!  When ReflCoef%cGround_Plane /= cFreeSpace:
!   Image left-node:  vL_img  = [ vL(1),  vL(2), −vL(3) ]   (z-reflection)
!   Image uHat:       uH_img  = [ uH(1),  uH(2), −uH(3) ]   (z-component negated)
!   Image phase:      phi0_img = dot(vkout, vL_img)
!   Image u:          u_img    = dot(vkout, uH_img) * L
!   Image integral:   I_int_img = rad_integral(u_img, L, iEnd)
!   Image contribution weighted by Fresnel R(iPol) per polarisation.
!
!  R = ReflCoef%FRC(thr(iAng)) — per-angle Fresnel coefficient.
!  R(1) → E_theta (TM/vertical), R(2) → E_phi (TE/horizontal).
!
!==============================================================================
!  ANGLE_CUT CONVENTIONS
!==============================================================================
!
!  vK(:,iAng)       unit vector TOWARD origin (= −r̂), dimensionless
!  uPol(:,iAng,1)   θ̂ (theta-hat): E_theta polarisation direction
!  uPol(:,iAng,2)   φ̂ (phi-hat):   E_phi   polarisation direction
!  thr(iAng)        theta in radians (co-elevation from zenith)
!  phr(iAng)        phi   in radians
!
!  vkout = −vK(:,iAng) * bk   [rad/m, outward propagation vector]
!
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m,    only: SEGMENT_TYPE, NODE_TYPE
   use basis_builder_m,           only: BASIS2_TYPE
   use angle_cut_m,          only: ANGLE_CUT_TYPE
   use fresnel_reflection_m, only: Fresnel_Reflection_Coef_Type, cFreeSpace

   implicit none; private

   public :: pattern_v2

   !  UTINY: threshold for switching to Taylor expansion in rad_integral.
   !  |u| < UTINY means the segment is nearly perpendicular to the observation
   !  direction (rhat ⊥ uHat) OR the segment is electrically very short.
   !  Value 1e-4 rad gives Taylor error < 1e-16 at the u³ term.
   real, parameter :: UTINY = 1.0e-4


contains

!==============================================================================
!  pattern_v2: compute far-field amplitude Er(nAng, 2).
!
!  Input:
!   Basis2(:)  -- rooftop basis functions (BASIS2_TYPE array)
!   Segs(:)    -- mesh segments (for uHat, length)
!   Nodes(:)   -- mesh nodes (for left-node position vL)
!   cur(:)     -- complex current coefficients, cur(m) for basis function m
!   bk         -- free-space wave number k = 2π/λ [rad/m]
!   AngleCut   -- angle grid with vK and uPol precomputed
!   ReflCoef   -- Fresnel ground-plane object (must be initialised)
!
!  Output (allocated here):
!   Er(nAng, 2) -- far-field amplitude [V·m]
!                  Er(:,1) = E_theta component
!                  Er(:,2) = E_phi   component
!                  NOT normalised by sqrt(P_in); pattern_3d handles that.
!
!  Loop structure:
!   outer: iAng = 1..nAng     (observation directions)
!     inner: m = 1..nB        (basis functions)
!       inner: h = 1,2        (halves of basis function m)
!         direct contribution + image contribution (if ground present)
!
!  All floating-point arithmetic in single precision (default real).
!  Complex precision follows basic_header_m wp parameter.
!==============================================================================
   subroutine pattern_v2(Basis2, Segs, Nodes, cur, bk, AngleCut, ReflCoef, Er)

      type(BASIS2_TYPE),                  intent(in)    :: Basis2(:)
      type(SEGMENT_TYPE),                 intent(in)    :: Segs(:)
      type(NODE_TYPE),                    intent(in)    :: Nodes(:)
      complex,                            intent(in)    :: cur(:)
      real,                               intent(in)    :: bk
      type(ANGLE_CUT_TYPE),               intent(in)    :: AngleCut
      type(Fresnel_Reflection_Coef_Type), intent(inout) :: ReflCoef
      complex, allocatable,               intent(out)   :: Er(:,:)

      integer :: nAng, nB, iAng, m, h, iPol
      logical :: hasGround
      complex :: R(2)

      ! Per-angle temporaries
      real :: vkout(3)          ! outward propagation vector [rad/m]

      ! Per-half temporaries (direct contribution)
      real    :: vL(3)          ! left-node position [m]
      real    :: uH(3)          ! segment unit vector
      real    :: L_h            ! segment length [m]
      real    :: effS            ! effSign ∈ {±1}
      real    :: phi0            ! phase at left node [rad]
      real    :: u               ! phase excursion across segment [rad]
      complex :: I_int           ! analytical radiation integral [m]
      complex :: cFac            ! combined prefactor for this half

      ! Image temporaries
      real    :: vL_img(3)      ! reflected left-node [m]
      real    :: uH_img(3)      ! reflected uHat
      real    :: phi0_img        ! image phase at reflected left node [rad]
      real    :: u_img           ! image phase excursion [rad]
      complex :: I_int_img       ! image radiation integral [m]

      ! Prefactor: −j*k*ETA0/(4π)
      ! = -(j*k * 376.7303) / 12.566 ≈ −j*k*29.98
      complex :: prefac

      !--------------------------| start |--------------------------------------------

      nAng = AngleCut%nAng
      nB   = size(Basis2)

      allocate(Er(nAng, 2))
      Er = zZERO

      prefac    = -zIMAG * bk * ETA0 / FOURPI
      hasGround = (ReflCoef%cGround_Plane /= cFreeSpace)

      do iAng = 1, nAng

         ! Outward propagation vector: vK points toward origin → negate for outward
         vkout = -AngleCut%vK(:, iAng) * bk

         ! Fresnel coefficients at this elevation angle (zero if free space)
         if (hasGround) then
            R = ReflCoef%FRC(AngleCut%thr(iAng))
         else
            R = zZERO
         end if

         do m = 1, nB

            do h = 1, 2

               associate( segHalf => Basis2(m)%half(h),           &
                          S       => Segs(Basis2(m)%half(h)%iSeg) )

                  L_h  = S%length
                  uH   = S%uHat
                  effS = segHalf%effSign

                  ! Phase reference at left node of this segment.
                  ! Earlier centroid-based form used vCtr = vL + L/2 * uHat;
                  ! left-node lookup is exact and slightly more readable.
                  vL = Nodes(S%iLeftNode)%v

                  phi0 = dot_product(vkout, vL)          ! phase at left node
                  u    = dot_product(vkout, uH) * L_h    ! phase excursion [rad]

                  I_int = rad_integral(u, L_h, segHalf%iEnd)

                  ! Combined factor: prefac * effSign * cur(m) * exp(j*phi0) * I_int
                  cFac = prefac * effS * cur(m) * exp(zIMAG*phi0) * I_int

                  ! Project onto each polarisation direction
                  do iPol = 1, 2
                     Er(iAng, iPol) = Er(iAng, iPol) &
                                    + cFac * dot_product(uH, AngleCut%uPol(:, iAng, iPol))
                  end do

                  ! ---- Ground image ----
                  if (hasGround) then
                     ! Reflect source below the z=0 ground plane
                     vL_img = [ vL(1),  vL(2), -vL(3) ]   ! z-component negated
                     uH_img = [ uH(1),  uH(2), -uH(3) ]   ! z-component of uHat negated

                     phi0_img  = dot_product(vkout, vL_img)
                     u_img     = dot_product(vkout, uH_img) * L_h

                     I_int_img = rad_integral(u_img, L_h, segHalf%iEnd)

                     cFac = prefac * effS * cur(m) &
                            * exp(zIMAG*phi0_img) * I_int_img

                     ! Image weighted by per-polarisation Fresnel coefficient R(iPol)
                     do iPol = 1, 2
                        Er(iAng, iPol) = Er(iAng, iPol) &
                                       + R(iPol) * cFac &
                                       * dot_product(uH_img, AngleCut%uPol(:, iAng, iPol))
                     end do
                  end if

               end associate

            end do ! h = 1,2

         end do ! m = 1,nB

      end do ! iAng

   end subroutine pattern_v2


!==============================================================================
!  rad_integral: analytical radiation integral for one rooftop half.
!
!    I = L * ∫₀¹ f(t) * exp(j*u*t) dt
!
!  where:
!    u     = dot(vkout, uHat) * L   [rad, net phase across segment]
!    L     = segment length [m]
!    iEnd  = 2 → f(t) = t          (ascending, hub at right)
!    iEnd  = 1 → f(t) = 1 − t      (descending, hub at left)
!
!  Closed-form (|u| ≥ UTINY):
!   iEnd=2:  I = L * [ eju/ju  − (eju−1)/ju² ]
!   iEnd=1:  I = L * [ −1/ju   + (eju−1)/ju² ]
!
!  Taylor series (|u| < UTINY):
!   iEnd=2:  I/L = 1/2 + j*u/3   − u²/8   − j*u³/30   + O(u⁴)
!   iEnd=1:  I/L = 1/2 + j*u/6   − u²/24  − j*u³/120  + O(u⁴)
!
!  Derivation of Taylor coefficients:
!   I/L = Σₙ (ju)ⁿ/n! * ∫₀¹ tⁿ * f(t) dt
!   iEnd=2: ∫₀¹ tⁿ⁺¹ dt          = 1/(n+2)
!   iEnd=1: ∫₀¹ (1−t)*tⁿ dt      = 1/((n+1)(n+2))
!
!  Threshold UTINY = 1e-4: Taylor series error at u³ term < (1e-4)⁴/4! ≈ 4e-19.
!
!  The function is pure (no side effects) and called O(nAng * nBasis) times.
!==============================================================================
   pure function rad_integral(u, L, iEnd) result(I)

      real,    intent(in) :: u      ! phase excursion = dot(vkout, uHat) * L [rad]
      real,    intent(in) :: L      ! segment length [m]
      integer, intent(in) :: iEnd   ! 1=descending,  2=ascending

      complex :: I
      complex :: ju, eju

      if (abs(u) >= UTINY) then

         ! Exact closed-form integrals
         ju  = zIMAG * real(u, kind(ONE))
         eju = exp(ju)

         if (iEnd == 2) then
            ! iEnd=2 (ascending, f=t):
            !   ∫₀¹ t*exp(jut)dt = exp(ju)/(ju) - (exp(ju)-1)/(ju)²
            I = L * ( eju/ju - (eju - zONE)/(ju*ju) )
         else
            ! iEnd=1 (descending, f=1-t):
            !   ∫₀¹ (1-t)*exp(jut)dt = -1/(ju) + (exp(ju)-1)/(ju)²
            I = L * ( -zONE/ju + (eju - zONE)/(ju*ju) )
         end if

      else

         ! Taylor expansion — avoids 0/0 when rhat ⊥ uHat or L→0
         if (iEnd == 2) then
            ! real part: 1/2 - u²/8,   imag part: u/3 - u³/30
            I = L * cmplx( 0.5 - u*u/8.0,    u/3.0  - u*u*u/30.0  )
         else
            ! real part: 1/2 - u²/24,  imag part: u/6 - u³/120
            I = L * cmplx( 0.5 - u*u/24.0,   u/6.0  - u*u*u/120.0 )
         end if

      end if

   end function rad_integral

end module pattern_v2_m
