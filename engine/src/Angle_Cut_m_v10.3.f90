module angle_cut_m

!==============================================================================
!  angle_cut_m — spherical observation angle grid for NeoMoM
!
!  Purpose:
!   Define ANGLE_CUT_TYPE, the container for one angular grid (either a 1-D
!   elevation/azimuth cut or a full 2-D 3-D pattern grid), and compute the
!   three direction vectors required by the far-field and excitation kernels:
!     vK      — propagation direction unit vector (toward origin = -r̂)
!     uPol(:,1) = θ̂  (theta polarisation direction)
!     uPol(:,2) = φ̂  (phi   polarisation direction)
!
!  Two operating modes:
!   1. CUT mode  (init_cut → Angle_Cut_Compute)
!      Single elevation or azimuth cut.  AngleFixed is held constant;
!      the variable angle sweeps AngleMin to AngleMax in nAng steps.
!      Used for 2-D pattern cuts (currently commented out in ANTENNA_TYPE).
!
!   2. 3-D mode  (init_3D_pattern)
!      Full or upper-hemisphere grid.  theta-outer, phi-inner loop order.
!      iAng = (iTheta-1)*nPhi + iPhi
!      Used by pattern_3d and power_check.
!
!==============================================================================
!  SPHERICAL COORDINATE SYSTEM
!==============================================================================
!
!  NeoMoM uses the physics/antenna convention:
!   theta  -- co-elevation angle from +z axis   [0°, 180°]
!   phi    -- azimuth angle from +x toward +y   [0°, 360°)
!
!  Cartesian unit vectors from (theta, phi):
!   r̂    = [ sin(θ)cos(φ),  sin(θ)sin(φ),  cos(θ) ]
!   θ̂    = [ cos(θ)cos(φ),  cos(θ)sin(φ), -sin(θ) ]   (E_theta direction)
!   φ̂    = [ -sin(φ),        cos(φ),         0      ]   (E_phi   direction)
!
!  Propagation direction (vK):
!   vK = -r̂ = [ -sin(θ)cos(φ), -sin(θ)sin(φ), -cos(θ) ]
!   vK points TOWARD the coordinate origin.  In pattern_v2_m, the outward
!   propagation vector used in the radiation integral is:
!     vkout = -vK * bk   [points away from origin, units rad/m]
!
!  Arrays stored:
!   thr(iAng)        -- theta [radians]   (r = radians)
!   phr(iAng)        -- phi   [radians]
!   vK(3,iAng)       -- unit propagation vector toward origin
!   uPol(3,iAng,1)   -- θ̂ (theta-hat polarisation)
!   uPol(3,iAng,2)   -- φ̂ (phi-hat   polarisation)
!   angle_pairs(2,iAng) -- [theta_deg, phi_deg] for peak-gain reporting
!
!==============================================================================
!  3-D GRID LAYOUT (init_3D_pattern)
!==============================================================================
!
!  Grid nodes:
!   theta: theta_min, theta_min+del, ..., theta_max  (nTheta points inclusive)
!   phi:   0°, phi_del, ..., phi_max                 (nPhi   points inclusive)
!
!  Implementation note:
!   The grid formula uses (iTheta-1)*theta_del and (iPhi-1)*phi_del, which
!   effectively sets theta_start = phi_start = 0° regardless of the stored
!   theta_min/phi_min fields.  This is correct for NeoMoM because pattern_3d
!   always sets theta_min = phi_min = 0.0 before calling init_3D_pattern.
!   If non-zero theta_min or phi_min is ever required, the loop should use
!   theta_min + (iTheta-1)*theta_del.
!
!  Total points:  nAng = nTheta * nPhi
!  Flat index:    iAng = (iTheta-1)*nPhi + iPhi
!
!  Phi-endpoint duplication:
!   For a full azimuth sweep phi_min=0°, phi_max=360°, the first and last phi
!   samples (iPhi=1 and iPhi=nPhi) point in the same direction (0°=360°).
!   power_check corrects for this with trapezoidal phi weighting.
!
!==============================================================================
!  ROTATION UTILITIES
!==============================================================================
!
!  Three_Axis_Rotation, build_rotation_matrix, normalize_vector implement
!  Rodrigues's rotation formula for composing three arbitrary-axis rotations.
!  These are NOT currently connected to the active pattern or excitation path
!  (the roll-axis commented code in Angle_Cut_Compute would use them).
!  Available for future use in tilted-platform or conformal-array applications.
!
!==============================================================================

   use basic_header_m
   use vector_and_utility_m

   implicit none; private

   public ANGLE_CUT_TYPE, Angle_Cut_Array_Input, Angle_Cut_Read_v1


!------------------------------------------------------------------------------
!  ANGLE_CUT_TYPE: one observation angle grid.
!
!  Cut-mode fields (used by init_cut / Angle_Cut_Compute):
!   AngleFixed  -- held-constant angle [deg]: phi for elevation cut, theta for azimuth
!   AngleMin    -- sweep start  [deg]
!   AngleMax    -- sweep end    [deg]
!   AngleDelta  -- step size    [deg] = (AngleMax-AngleMin)/(nAng-1)
!   cCutType    -- 'ELEVATION' or 'AZIMUTH' (character constants from basic_header_m)
!
!  3-D pattern fields (used by init_3D_pattern):
!   nTheta      -- number of theta samples
!   nPhi        -- number of phi   samples
!   theta_min/max/del -- theta range and step [deg]
!   phi_min/max/del   -- phi   range and step [deg]
!
!  Shared / computed fields:
!   nAng            -- total number of directions  (nTheta*nPhi for 3D, or sweep count)
!   thr(nAng)       -- theta [radians]
!   phr(nAng)       -- phi   [radians]
!   vK(3,nAng)      -- unit propagation vector toward origin
!   uPol(3,nAng,2)  -- polarisation unit vectors: uPol(:,:,1)=θ̂, uPol(:,:,2)=φ̂
!   angle_pairs(2,nAng) -- [theta,phi] in degrees; used for peak-gain direction lookup
!------------------------------------------------------------------------------
   type ANGLE_CUT_TYPE

      ! ---- cut-mode parameters ----
      real                  :: AngleFixed, AngleMin, AngleMax, AngleDelta
      character(maxChar20)  :: cCutType = cAZIMUTH   ! 'AZIMUTH' or 'ELEVATION'

      ! ---- 3-D pattern grid parameters (set before init_3D_pattern) ----
      integer :: nTheta = 0, nPhi = 0
      real    :: Theta_max = 90.0,  theta_min = 0.0
      real    :: phi_max   = 360.0, phi_min   = 0.0
      real    :: theta_del = 1.0,   phi_del   = 5.0  ! step sizes [deg]

      ! ---- computed arrays (allocated by Angle_Cut_Allocate) ----
      integer               :: nAng
      real, allocatable     :: thr(:), phr(:)           ! angles [radians]
      real, allocatable     :: vK(:, :)                 ! vK(3,nAng), toward origin
      real, allocatable     :: uPol(:, :, :)            ! uPol(3,nAng,iPol): 1=θ̂, 2=φ̂
      real, allocatable     :: angle_pairs(:, :)        ! angle_pairs(2,nAng) [degrees]

   contains
      procedure :: Angle_Cut_Print
      procedure :: AngDeallocate
      procedure :: Angle_Cut_Compute   ! build thr/phr/vK/uPol from cut parameters
      procedure :: Angle_Cut_Allocate  ! allocate thr, phr, vK, uPol, angle_pairs
      procedure :: Angle_Cut_vk_uPol   ! compute vK/uPol from existing thr/phr
      procedure :: init_cut            ! set cut parameters (does NOT allocate)
      procedure :: init_3D_pattern     ! build full theta×phi grid

   end type ANGLE_CUT_TYPE


contains

!==============================================================================
!  init_3D_pattern: build a complete theta×phi spherical grid.
!
!  Preconditions (set by caller, typically pattern_3d):
!   this%theta_min, theta_max, theta_del
!   this%phi_min,   phi_max,   phi_del
!
!  Actions:
!   1. Compute nTheta = nint((theta_max - theta_min)/theta_del) + 1
!      Compute nPhi   = nint((phi_max   - phi_min  )/phi_del  ) + 1
!   2. Allocate thr, phr, vK, uPol, angle_pairs
!   3. Fill angle_pairs(:,iAng) in degrees (theta outer, phi inner loop)
!      theta = (iTheta-1)*theta_del,  phi = (iPhi-1)*phi_del
!      (Assumes theta_min = phi_min = 0; see module header note)
!   4. Convert thr, phr to radians
!   5. Call Angle_Cut_vk_uPol to compute vK and uPol
!
!  Result layout:  iAng = (iTheta-1)*nPhi + iPhi   (theta outer, phi inner)
!  This matches the loop in power_check:  iPhi = mod(iAng-1, nPhi) + 1
!==============================================================================
   subroutine init_3D_pattern(this)

      class(ANGLE_CUT_TYPE) :: this

      integer :: nTheta, nPhi, nAng, iAng, iTheta, iPhi
      real    :: theta, phi

      nTheta = nint((this%theta_max - this%theta_min) / this%theta_del) + 1
      nPhi   = nint((this%phi_max   - this%phi_min  ) / this%phi_del  ) + 1
      nAng   = nTheta * nPhi

      this%nAng   = nAng
      this%nTheta = nTheta
      this%nPhi   = nPhi

      call this%Angle_Cut_Allocate(nAng)

      associate (thr => this%thr, phr => this%phr)

         theta = 0.0;  phi = 0.0;  iAng = 0

         do iTheta = 1, nTheta

            theta = (iTheta - 1) * this%theta_del

            do iPhi = 1, nPhi

               phi  = (iPhi - 1) * this%phi_del
               iAng = iAng + 1

               thr(iAng) = theta
               phr(iAng) = phi

               this%angle_pairs(1, iAng) = theta   ! [degrees] for peak reporting
               this%angle_pairs(2, iAng) = phi

            end do ! iPhi
         end do ! iTheta

         ! Convert to radians for all downstream trigonometry
         thr = thr * DTOR
         phr = phr * DTOR

         ! Compute vK and uPol from thr/phr
         call this%Angle_Cut_vk_uPol()

         this%nAng = nAng

      end associate

   end subroutine init_3D_pattern


!==============================================================================
!  init_cut: set cut-mode parameters (does NOT allocate or compute arrays).
!
!  Call Angle_Cut_Compute after this to build thr/phr/vK/uPol.
!
!  Parameters:
!   max, min    -- sweep angle range [deg]
!   nAng        -- number of sample points (step = (max-min)/(nAng-1))
!   fixed       -- held-constant angle [deg]
!   cCutType    -- 'ELEVATION' or 'AZIMUTH'
!==============================================================================
   subroutine init_cut(this, max, min, nAng, fixed, cCutType)

      class(ANGLE_CUT_TYPE), intent(inout) :: this
      real(wp),              intent(in)    :: max, min, fixed
      integer,               intent(in)    :: nAng
      character(len=*),      intent(in)    :: cCutType

      this%AngleFixed = fixed
      this%AngleMin   = min
      this%AngleMax   = max
      this%AngleDelta = (max - min) / real(nAng - 1, wp)
      this%nAng       = nAng
      this%cCutType   = cCutType

   end subroutine init_cut


!==============================================================================
!  Angle_Cut_vk_uPol: compute vK(3,nAng) and uPol(3,nAng,2) from thr/phr.
!
!  Called by init_3D_pattern after thr/phr are filled and converted to radians.
!  Also usable standalone when thr/phr are loaded from an external file.
!
!  Formulas:
!   vK(:,i)   = [ -sin(θ)cos(φ), -sin(θ)sin(φ), -cos(θ) ]   (toward origin)
!   uPol(:,i,1) = θ̂ = [  cos(θ)cos(φ),  cos(θ)sin(φ), -sin(θ) ]
!   uPol(:,i,2) = φ̂ = [ -sin(φ),          cos(φ),        0     ]
!
!  Precondition: thr and phr allocated and in radians; vK and uPol allocated.
!==============================================================================
   subroutine Angle_Cut_vk_uPol(this)

      class(ANGLE_CUT_TYPE) :: this

      real(wp)  :: cth, sth, cphi, sphi
      integer   :: iAng

      do iAng = 1, size(this%thr)

         cTh  = cos(this%thr(iAng))
         sTh  = sin(this%thr(iAng))
         cPhi = cos(this%phr(iAng))
         sPhi = sin(this%phr(iAng))

         ! vK = -r̂: propagation direction toward origin
         this%vK(1, iAng) = -sTh * cPhi
         this%vK(2, iAng) = -sTh * sPhi
         this%vK(3, iAng) = -cTh

         ! uPol(:,:,1) = θ̂: theta polarisation direction
         this%uPol(1, iAng, 1) =  cTh * cPhi
         this%uPol(2, iAng, 1) =  cTh * sPhi
         this%uPol(3, iAng, 1) = -sTh

         ! uPol(:,:,2) = φ̂: phi polarisation direction (no z-component)
         this%uPol(1, iAng, 2) = -sPhi
         this%uPol(2, iAng, 2) =  cPhi
         this%uPol(3, iAng, 2) =  ZERO

      end do

   end subroutine Angle_Cut_vk_uPol


!==============================================================================
!  Angle_Cut_Compute: build complete cut arrays from stored parameters.
!
!  Used in CUT mode after init_cut (or direct field assignment + nAng setting).
!  Deallocates any existing arrays, re-allocates, then fills thr/phr/vK/uPol.
!
!  Cut sweep:
!   cAZIMUTH:   phi sweeps AngleMin..AngleMax;  theta = AngleFixed
!   cELEVATION: theta sweeps AngleMin..AngleMax; phi   = AngleFixed
!
!  Note: the commented-out Roll_Matrix_X_axis code would rotate the pattern
!  reference frame about the x-axis.  Not currently active; see module header.
!==============================================================================
   subroutine Angle_Cut_Compute(this)

      class(ANGLE_CUT_TYPE), intent(inout) :: this

      real(wp)  :: cTh, cPhi, sTh, sPhi, theta, phi
      integer   :: iAng, nAng

      if (allocated(this%thr))        deallocate (this%thr)
      if (allocated(this%phr))        deallocate (this%phr)
      if (allocated(this%vK))         deallocate (this%vK)
      if (allocated(this%uPol))       deallocate (this%uPol)
      if (allocated(this%angle_pairs)) deallocate (this%angle_pairs)

      nAng = this%nAng
      call this%Angle_Cut_Allocate(nAng)

      do iAng = 1, this%nAng

         ! Sweep the variable angle; hold the fixed angle constant
         select case (this%cCutType)
         case (cAZIMUTH)
            phi   = this%AngleMin + (iAng - 1) * this%AngleDelta
            theta = this%AngleFixed
         case (cELEVATION)
            theta = this%AngleMin + (iAng - 1) * this%AngleDelta
            phi   = this%AngleFixed
         case default
            call FatalError('Angle_Cut_Compute: cCutType out of range', '', 0)
         end select

         this%angle_pairs(1, iAng) = theta    ! [degrees]
         this%angle_pairs(2, iAng) = phi

         this%thr(iAng) = theta * DTOR
         this%phr(iAng) = phi   * DTOR

         cTh  = cos(this%thr(iAng))
         sTh  = sin(this%thr(iAng))
         cPhi = cos(this%phr(iAng))
         sPhi = sin(this%phr(iAng))

         ! vK: toward origin
         this%vK(1, iAng) = -sTh * cPhi
         this%vK(2, iAng) = -sTh * sPhi
         this%vK(3, iAng) = -cTh

         ! θ̂ and φ̂ polarisation directions
         this%uPol(1, iAng, 1) =  cTh * cPhi
         this%uPol(2, iAng, 1) =  cTh * sPhi
         this%uPol(3, iAng, 1) = -sTh

         this%uPol(1, iAng, 2) = -sPhi
         this%uPol(2, iAng, 2) =  cPhi
         this%uPol(3, iAng, 2) =  ZERO

      end do

   end subroutine Angle_Cut_Compute


!==============================================================================
!  Angle_Cut_Allocate: allocate angle arrays for nAng directions.
!
!  Deallocates existing thr/phr/vK/uPol if allocated, then re-allocates.
!  angle_pairs is handled separately (separate allocated check).
!
!  Called by: init_3D_pattern, Angle_Cut_Compute, Angle_Cut_Read_v1,
!             Angle_Cut_Array_Input.
!==============================================================================
   subroutine Angle_Cut_Allocate(this, nAng)

      class(ANGLE_CUT_TYPE), intent(inout) :: this
      integer, intent(in) :: nAng

      if (allocated(this%thr)) deallocate (this%thr, this%phr, this%vk, this%uPol)
      allocate (this%thr(nAng), this%phr(nAng), this%vk(3, nAng), this%uPol(3, nAng, 2))

      if (allocated(this%angle_pairs)) deallocate (this%angle_pairs)
      allocate (this%angle_pairs(2, nAng))

   end subroutine Angle_Cut_Allocate


!==============================================================================
!  AngDeallocate: free all allocated angle arrays.
!==============================================================================
   subroutine AngDeallocate(this)

      class(ANGLE_CUT_TYPE), intent(inout) :: this

      if (allocated(this%thr)) deallocate (this%thr, this%phr, this%vk, this%uPol)

   end subroutine AngDeallocate


!==============================================================================
!  Angle_Cut_Read_v1: read multiple angle cuts from a jfs/NeoMoM text file.
!
!  Format expected in the file at current position:
!   [Angle Cuts]
!   nCuts = <n>
!   for each cut:
!     line: = <aMin> <aMax> <nAng>
!     line: = ELEVATION or AZIMUTH
!     line: = <AngleFixed>
!
!  Calls Angle_Cut_Compute for each cut after reading.
!  FatalError on unrecognised cut type (goto 9000).
!==============================================================================
   subroutine Angle_Cut_Read_v1(iU, Angle_Cuts)

      type(ANGLE_CUT_TYPE), allocatable, intent(out) :: Angle_Cuts(:)
      integer, intent(in) :: iU

      integer       :: nAng, nAngleCuts, iCut
      real(wp)      :: aMin, aMax, AngleDelta
      character(80) :: cLine, cLineOut
      character(1)  :: ch
      logical       :: bRet

      character(len=*), parameter :: cSub = 'In subroutine Angle_Cut_Array_Input : '

      bRet = position_file_to_keyword(iU, '[Angle Cuts]')

      nAngleCuts = real_value_after_equal('nCuts', iU)
      allocate (Angle_Cuts(nAngleCuts))

      do iCut = 1, nAngleCuts

         read (iU, '(A)') cLine
         call Text_to_Right('=', cLineOut, cLine, bRet)
         read (cLineOut, *) aMin, aMax, nAng

         if (nAng == 1) then
            AngleDelta = 0
         else
            AngleDelta = (aMax - aMin) / (nAng - 1)
         end if

         if ((aMin == aMax) .and. (nAng /= 1)) &
            call fatalError(cSub//'Angle min/max the same with nAng /= 1', '', 0)

         Angle_Cuts(iCut)%AngleMin   = aMin
         Angle_Cuts(iCut)%AngleMax   = aMax
         Angle_Cuts(iCut)%nAng       = nAng
         Angle_Cuts(iCut)%AngleDelta = AngleDelta

         ! Cut type: 'E' or 'e' → ELEVATION; 'A' or 'a' → AZIMUTH
         read (iU, '(A)') cLine
         call Text_to_Right('=', cLineOut, cLine, bRet)
         cLine = adjustL(cLineOut)
         ch    = cLineOut(1:1)

         if (ch == 'E' .or. ch == 'e') then
            Angle_Cuts(iCut)%cCutType = cELEVATION
         elseif (ch == 'A' .or. ch == 'a') then
            Angle_Cuts(iCut)%cCutType = cAZIMUTH
         else
            goto 9000
         end if

         read (iU, '(A)') cLine
         call Text_to_Right('=', cLineOut, cLine, bRet)
         read (cLineOut, *) Angle_Cuts(iCut)%AngleFixed

         call Angle_Cuts(iCut)%Angle_Cut_Compute()

      end do

      return

9000  call FatalError('Error in input file reading Angle Cut Data', ' ', 0)

   end subroutine Angle_Cut_Read_v1


!==============================================================================
!  Angle_Cut_Array_Input: read multiple angle cuts from a free-format text file.
!
!  Searches for keyword 'Angle' (or 'TxAngle' if bTxAngles is present and .TRUE.)
!  then reads:
!   line 1: <nAngleCuts>
!   for each cut:
!     line: <aMin> <aMax> <nAng>
!     line: ELEVATION or AZIMUTH (first character used)
!     line: <AngleFixed>
!
!  Note: Angle_Cut_Compute is commented out — caller must call it separately.
!==============================================================================
   subroutine Angle_Cut_Array_Input(Angle_Cuts, iU, bTxAngles)

      type(ANGLE_CUT_TYPE), allocatable, intent(out) :: Angle_Cuts(:)
      integer, intent(in)           :: iU
      logical, optional, intent(in) :: bTxAngles

      integer       :: nAng, nAngleCuts, iErr, iCut
      real(wp)      :: aMin, aMax, AngleDelta
      character(80) :: cLine
      character(1)  :: ch

      character(len=*), parameter :: cSub = 'In subroutine Angle_Cut_Array_Input : '

      ! Position file to the correct keyword
      if (present(bTxAngles)) then
         if (bTxAngles) then
            if (.not. position_file_to_keyword(iU, 'TxAngle')) &
               call fatalError('Failed to read Tx Angle Cuts in input file', '', 0)
         else
            if (.not. position_file_to_keyword(iU, 'Angle')) &
               call fatalError('Failed to read Rx Angle Cuts in input file', '', 0)
         end if
      else
         if (.not. position_file_to_keyword(iU, 'Angle')) &
            call fatalError('Failed to read Rx Angle Cuts in input file', '', 0)
      end if

      read (iU, '(a)', err=9000) cLine
      read (cLine, *, iostat=iErr) nAngleCuts

      allocate (Angle_Cuts(nAngleCuts))

      do iCut = 1, nAngleCuts

         read (iU, *, err=9000) aMin, aMax, nAng

         if (nAng == 1) then
            AngleDelta = 0
         else
            AngleDelta = (aMax - aMin) / (nAng - 1)
         end if

         if ((aMin == aMax) .and. (nAng /= 1)) &
            call fatalError(cSub//'Angle min/max the same with nAng /= 1', '', 0)

         Angle_Cuts(iCut)%AngleMin   = aMin
         Angle_Cuts(iCut)%AngleMax   = aMax
         Angle_Cuts(iCut)%nAng       = nAng
         Angle_Cuts(iCut)%AngleDelta = AngleDelta

         ! Cut type: first character of next line
         read (iU, *, err=9000, end=9000) cLine
         cLine = adjustL(cLine)
         ch    = cLine(1:1)

         if (ch == 'E' .or. ch == 'e') then
            Angle_Cuts(iCut)%cCutType = cELEVATION
         elseif (ch == 'A' .or. ch == 'a') then
            Angle_Cuts(iCut)%cCutType = cAZIMUTH
         else
            goto 9000
         end if

         read (iU, *, err=9000) Angle_Cuts(iCut)%AngleFixed
         ! Note: Angle_Cut_Compute not called here; caller must invoke it.

      end do

      return

9000  call FatalError('Error in input file reading Angle Cut Data', ' ', 0)

   end subroutine Angle_Cut_Array_Input


!==============================================================================
!  Angle_Cut_Print: formatted console output of angle cut parameters.
!
!  cSolveType controls which fields are printed (MONOSTATIC, ANTENNA, etc.).
!  AngleOffset (optional) is printed for cFIXED_ANGLE_BISTATIC.
!  cRxAngles  (optional) distinguishes Tx vs. Rx labels in MULTI_BISTATIC.
!==============================================================================
   subroutine Angle_Cut_Print(this, cSolveType, cRxAngles, AngleOffset)

      class(ANGLE_CUT_TYPE), intent(in) :: this

      character(20),          intent(in)           :: cSolveType
      real(wp),     optional, intent(in)           :: AngleOffset
      character(20), optional, intent(in)          :: cRxAngles

      character(80) :: cLine
      character(20) :: cExcitationType = 'none'

      cExcitationType = cSolveType

      if (cExcitationType == cMONOSTATIC) then
         write (cLine, 900) '  Number of RHS = nAng * 2   : ', 2*this%nAng; call out(cLine)

      elseif (cExcitationType == cRHS_DIPOLE .or. cExcitationType == cANTENNA) then
         write (cLine, 900) '   ANTENNA Pattern, Dipole Excitations '

      elseif (cExcitationType == cDIPOLE_MONOSTATIC) then
         write (cLine, 900) '   DIPOLE    nRHS = nAng * 2   : ', 2*this%nAng; call out(cLine)

      elseif (cExcitationType == cMULTI_BISTATIC) then
         if (.not. present(cRxAngles)) then
            write (cLine, 900) '   Tx nRHS = nAng * 2   : ', 2*this%nAng; call out(cLine)
         else
            write (cLine, 900) '   Rx Angles,  nRHS = nAng * 2   : ', 2*this%nAng; call out(cLine)
         end if

      elseif (cExcitationType == cPSM_PATTERN) then
         write (cLine, 900) '   PSM Pattern '

      elseif (cExcitationType == cFIXED_ANGLE_BISTATIC) then
         write (cLine, 905) AngleOffset; call out(cLine)

      else
         call fatalError('error: excitation type not defined', '', 0)
      end if

      call out('')

      if (cExcitationType /= cBISTATIC .and. cExcitationType /= cRHS_DIPOLE) then
         write (cLine, 903) '   Angle Cut                   : ', this%cCutType;  call out(cLine)
         write (cLine, 902) '   Fixed Angle                 : ', this%AngleFixed; call out(cLine)
         write (cLine, 900) '   Number of Pattern points    : ', this%nAng;       call out(cLine)
         write (cLine, 902) '   Var angle (min,max)         : ', this%AngleMin, this%AngleMax
         call out(cLine)
         call out('')
      end if

900   format(A, T36, I0)
902   format(A, T36, G0.3, 3x, G0.3)
903   format(A, T36, A)
905   format('   Fixed Angle Offset =', G0.3)

   end subroutine Angle_Cut_Print


!==============================================================================
!  Three_Axis_Rotation: compose three Rodrigues rotations.
!
!  Computes:  R = R3 * R2 * R1  (applied right-to-left in order iOrder)
!
!  Inputs:
!   u1, u2, u3   -- rotation axes (normalised in-place)
!   ang1..ang3   -- rotation angles [radians] about respective axes
!   iOrder(3)    -- application order, e.g. [1,2,3] → R3(R2(R1(v)))
!
!  Not currently connected to the active pattern path.
!  Intended for future tilted-platform or conformal-array applications.
!==============================================================================
   subroutine Three_Axis_Rotation(R, iOrder, u1, u2, u3, ang1, ang2, ang3)

      real(wp), intent(out)   :: R(3, 3)
      integer,  intent(in)    :: iOrder(3)
      real(wp), intent(inout) :: u1(3), u2(3), u3(3)
      real(wp), intent(in)    :: ang1, ang2, ang3

      real(wp) :: Rrot(3, 3, 3), Rtemp(3, 3)

      Rrot = ZERO

      call normalize_vector(u1)
      call normalize_vector(u2)
      call normalize_vector(u3)

      call build_rotation_matrix(u1, ang1, Rrot(:, :, 1))
      call build_rotation_matrix(u2, ang2, Rrot(:, :, 2))
      call build_rotation_matrix(u3, ang3, Rrot(:, :, 3))

      Rtemp = matmul(Rrot(:, :, iOrder(1)), Rrot(:, :, iOrder(2)))
      R     = matmul(Rtemp, Rrot(:, :, iOrder(3)))

   end subroutine Three_Axis_Rotation


!==============================================================================
!  normalize_vector: normalise v in-place; stop if zero-length.
!==============================================================================
   subroutine normalize_vector(v)

      real(wp), intent(inout) :: v(3)
      real(wp) :: norm

      norm = norm2(v)
      if (norm > 0.0_wp) then
         v = v / norm
      else
         print *, 'Error: zero-length axis vector'
         stop
      end if

   end subroutine normalize_vector


!==============================================================================
!  build_rotation_matrix: Rodrigues rotation matrix for unit axis u, angle theta.
!
!  R = I*cos(θ) + (1-cos(θ)) u⊗u + sin(θ) [u×]
!
!  where [u×] is the skew-symmetric cross-product matrix.
!  Input: u must be a unit vector (call normalize_vector first).
!         theta in radians.
!==============================================================================
   subroutine build_rotation_matrix(u, theta, R)

      real(wp), intent(in)  :: u(3), theta
      real(wp), intent(out) :: R(3, 3)

      real(wp) :: ux, uy, uz, c, s, one_c

      ux    = u(1);  uy = u(2);  uz = u(3)
      c     = cos(theta)
      s     = sin(theta)
      one_c = 1.0_wp - c

      R(1, 1) = c + ux*ux*one_c;        R(1, 2) = ux*uy*one_c - uz*s;    R(1, 3) = ux*uz*one_c + uy*s
      R(2, 1) = uy*ux*one_c + uz*s;     R(2, 2) = c + uy*uy*one_c;       R(2, 3) = uy*uz*one_c - ux*s
      R(3, 1) = uz*ux*one_c - uy*s;     R(3, 2) = uz*uy*one_c + ux*s;    R(3, 3) = c + uz*uz*one_c

   end subroutine build_rotation_matrix

end Module angle_cut_m
