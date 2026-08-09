module fresnel_reflection_m

!==============================================================================
!  fresnel_reflection_m
!
!  Purpose:
!   Compute Fresnel plane-wave reflection coefficients at a planar interface
!   between free space (upper half-space) and a lossy dielectric ground
!   (lower half-space).  Used by mesh_m for ground-plane image theory in both
!   the Z-matrix fill (zfill_m) and the far-field pattern (pattern_jfs_v2).
!
!==============================================================================
!  PHYSICS SUMMARY
!==============================================================================
!
!  Geometry:
!   Upper half-space: free space  (ε = ε0, μ = μ0)
!   Lower half-space: lossy ground (ε_eff = ε_r*ε0 - j*σ/ω, μ = μ0)
!   Interface at z = 0; plane wave incident from above at elevation angle θ
!   (θ measured from surface normal, i.e. θ=0 is normal incidence).
!
!  Both regions are non-magnetic (μr = 1).
!
!  Effective complex permittivity (relative):
!   ε_eff = ε_r - j * σ / (ω * ε0)
!
!   In NeoMoM bk = 2π/λ = ω/c, so ω = bk*c and ε0 = 1/(μ0*c²).
!   Substituting: σ/(ω*ε0) = σ*μ0*c/bk = σ*η0/bk  (η0 ≈ 376.73 Ω)
!
!   The code stores: epsilon = epsilon_ground - j*sigma*ETA0/bk
!   Units: [S/m]*[Ω]/[1/m] = [S/m]*[Ω*m] = dimensionless ✓
!
!  Fresnel reflection coefficients (normal-component form):
!
!   zRoot = sqrt(ε_eff - sin²θ)         [transmitted normal wave number, normalised]
!   Choose branch: Re(zRoot) ≥ 0        [physical attenuation into ground]
!
!   R_perp (TE, φ-pol):
!     R⊥ = (cosθ − zRoot) / (cosθ + zRoot)
!
!   R_parallel (TM, θ-pol):
!     R‖ = −(ε_eff*cosθ − zRoot) / (ε_eff*cosθ + zRoot)
!     NOTE: the sign follows the corrected form from Anastassiu (2003) Eq. A3.
!           A sign error in that reference has been corrected here.
!
!  Ground plane constants:
!   cFreeSpace = 'FREE_SPACE'  → R = (0, 0)     [no ground]
!   cPerfect   = 'PERFECT'     → R = (−1, −1)   [PEC; both polarisations]
!   cReal      = 'REAL'        → R from R_Compute [lossy dielectric]
!
!==============================================================================
!  USAGE SEQUENCE
!==============================================================================
!
!  1. Set mesh%Reflection_Coef%cGround_Plane = cFreeSpace / cPerfect / cReal
!     (and optionally epsilon_ground and sigma for cReal).
!  2. Call mesh%Reflection_Coef%init(bk) once per frequency.
!  3. Call mesh%Reflection_Coef%FRC(theta_rad) anywhere to get R(2).
!     R(1) = R_parallel (TM),  R(2) = R_perp (TE).
!
!  FRC(0.0) = grazing-angle coefficient used for the Z-matrix image term.
!  FRC(AngleCut%thr(iAng)) = per-angle coefficient used in pattern_jfs_v2.
!
!==============================================================================

   use basic_header_m

   implicit none
   private

   !  Ground plane type labels (character constants for namelist input)
   character(10), parameter :: cFreeSpace = 'FREE_SPACE'
   character(10), parameter :: cPerfect   = 'PERFECT'
   character(10), parameter :: cReal      = 'REAL'

   public :: cFreeSpace, cPerfect, cReal, Fresnel_Reflection_Coef_Type


!------------------------------------------------------------------------------
!  Fresnel_Reflection_Coef_Type: complete ground-plane state for one frequency.
!
!  bNotInitialized  -- guard flag; FRC() calls FatalError if init() not called.
!  cGround_Plane    -- type selector: 'FREE_SPACE', 'PERFECT', or 'REAL'.
!                      Set before init(); read by FRC() dispatch.
!  epsilon_ground   -- real part of relative permittivity εr (default 14.0,
!                      representative of dry soil).
!  sigma            -- conductivity [S/m] (default 0.005, dry soil).
!                      *** See DIMENSIONAL CHECK note in module header. ***
!  bk               -- wave number k = 2π/λ [1/m], set by init().
!  epsilon          -- complex effective εr computed by init():
!                      epsilon = epsilon_ground - j*sigma/bk
!  theta            -- last angle evaluated by R_Compute [rad]; stored for debug.
!  RefCoef(2)       -- last R(1:2) returned by R_Compute; default = (−1, −1) (PEC).
!------------------------------------------------------------------------------
   type :: Fresnel_Reflection_Coef_Type

      logical       :: bNotInitialized = .TRUE.
      character(10) :: cGround_Plane   = cFreeSpace       ! default: no ground

      complex       :: epsilon_ground  = cmplx(14.0, 0.0) ! εr: dry soil default
      real          :: sigma           = 0.005             ! conductivity [S/m]

      real          :: bk                                  ! k = 2π/λ [1/m]
      complex       :: epsilon                             ! ε_eff at current frequency

      real          :: theta    = ZERO                     ! last angle evaluated [rad]
      complex       :: RefCoef(2) = -zONE                 ! cached last result

   contains
      procedure :: init       ! set bk, compute epsilon; call once per frequency
      procedure :: FRC        ! dispatch: returns R(2) for given elevation angle
      procedure :: R_Compute  ! compute Fresnel R(2) at given angle (cReal only)

   end type Fresnel_Reflection_Coef_Type


contains

!==============================================================================
!  init: initialise for a given frequency.
!
!  Must be called once per frequency before FRC().
!  Sets bk, computes epsilon = epsilon_ground − j*sigma/bk.
!  cGround_Plane must be set by the caller before init().
!
!  epsilon = epsilon_ground - j*sigma*ETA0/bk
!  Derivation: σ/(ω*ε0) = σ*η0/bk, where η0=ETA0≈376.73 Ω.
!  Units: [S/m]*[Ω]/[1/m] = dimensionless ✓
!==============================================================================
   subroutine init(this, bk)

      class(Fresnel_Reflection_Coef_Type), intent(inout) :: this
      real, intent(in)                                   :: bk   ! k = 2π/λ [1/m]

      this%bk = bk

      ! Complex effective permittivity at this frequency
      ! NOTE: verify the sigma/bk factor — see dimensional check in module header
      this%epsilon = this%epsilon_ground - zIMAG * ( this%sigma * ETA0 ) /  this%bk 

      this%bNotInitialized = .FALSE.

   end subroutine init


!==============================================================================
!  FRC: return Fresnel reflection coefficients R(2) at elevation angle theta_rad.
!
!  Dispatches on cGround_Plane:
!   FREE_SPACE → R = (0, 0)       image theory disabled
!   PERFECT    → R = (−1, −1)     PEC ground (all polarisations reflect with −1)
!   REAL       → R_Compute(theta) lossy dielectric
!
!  R(1) = R_parallel (TM, θ-pol)
!  R(2) = R_perp     (TE, φ-pol)
!
!  FatalError if init() has not been called.
!==============================================================================
   function FRC(this, theta_rad_in) result(R)

      class(Fresnel_Reflection_Coef_Type), intent(inout) :: this
      real, intent(in)                                   :: theta_rad_in   ! elevation angle [rad]
      complex                                            :: R(2)

      real :: theta_rad
      
      theta_rad = theta_rad_in
      
      if (this%bNotInitialized) &
         call FatalError('Fresnel_Reflection_Coef_Type not initialized — call init() first', '', 0)

      select case (this%cGround_Plane)
      case (cFreeSpace); R = zZERO         ! no ground plane: no image contribution
      case (cPerfect);   R = -zONE         ! PEC: Γ = −1 for both polarisations
      case (cReal);      R = R_Compute(this, theta_rad)
      end select

   end function FRC


!==============================================================================
!  R_Compute: Fresnel coefficients for a lossy dielectric ground.
!
!  Input:
!   theta_rad  -- elevation angle measured from surface normal [rad]
!                 θ = 0 → normal incidence (vertical ray)
!                 θ = π/2 → grazing incidence (horizontal ray)
!
!  Algorithm:
!   1. cos_theta  = cos(theta_rad)
!   2. sin_theta_sq = sin(theta_rad)²
!   3. zRoot = sqrt(ε_eff − sin²θ),  branch: Re(zRoot) ≥ 0
!   4. R_perp     = (cosθ − zRoot)  / (cosθ + zRoot)
!   5. R_parallel = −(ε_eff*cosθ − zRoot) / (ε_eff*cosθ + zRoot)
!
!  Branch:
!   The default Fortran sqrt branch gives Im(zRoot) ≤ 0 for typical lossy
!   materials, but Re(zRoot) may be negative for some combinations of εr
!   and angle.  The explicit Re < 0 → negate step enforces physical attenuation
!   (wave must decay into the ground, not grow).
!
!  R_parallel sign:
!   The negative sign corrects a sign error in Anastassiu (2003) Eq. A3.
!   The form used here is consistent with the IEEE convention where TM
!   reflection coefficient is defined as R‖ = (n₂cosθᵢ − n₁cosθₜ) /
!   (n₂cosθᵢ + n₁cosθₜ), with the additional sign flip absorbed into the
!   ε*cosθ formulation for the case n₁=1 (free space above).
!
!  Result is stored in this%RefCoef for debugging and returned as R(2).
!==============================================================================
   function R_Compute(this, theta_rad) result(R)

      class(Fresnel_Reflection_Coef_Type), intent(inout) :: this
      real, intent(in)                                   :: theta_rad
      complex                                            :: R(2)

      complex :: eps, zRoot
      real    :: cos_theta, sin_theta_sq

      this%theta = theta_rad
      eps        = this%epsilon

      cos_theta    = cos(theta_rad)
      sin_theta_sq = sin(theta_rad)**2

      ! Transmitted normal wave-number component (normalised by k0)
      ! kz2 = sqrt(εr − sin²θ):  Re(kz2) ≥ 0 → physical attenuation into ground
      zRoot = sqrt(eps - sin_theta_sq)
      if (real(zRoot, wp) < ZERO) zRoot = -zRoot

      ! TE (perpendicular / φ-polarisation) reflection coefficient
      R(2) = (cos_theta - zRoot) / (cos_theta + zRoot)

      ! TM (parallel / θ-polarisation) reflection coefficient
      ! Note: negative sign corrects the sign error in Anastassiu (2003) Eq. A3
      R(1) = -(eps*cos_theta - zRoot) / (eps*cos_theta + zRoot)

      ! Cache for diagnostic access
      this%RefCoef = R

   end function R_Compute

end module fresnel_reflection_m
