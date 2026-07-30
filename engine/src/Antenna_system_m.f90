Module antenna_system_m

!==============================================================================
!  antenna_system_m — top-level driver module for NeoMoM
!
!  Purpose:
!   Defines ANTENNA_TYPE, the central object that owns the mesh, current
!   solution, frequency state, pattern results, and all I/O handles.
!   Also defines PATTERN_TYPE (the pattern result container).
!
!  Subroutines (bound to ANTENNA_TYPE):
!   Input        -- read .geo namelist file, build mesh, set excitations
!                   also parses optional command-line key=value flags
!   pattern_3d   -- adaptive 3-D far-field pattern, gain, CSV output
!   power_check  -- energy-conservation / radiation-efficiency check
!   data_out     -- formatted output panel + launch neomom_plot
!
!  Module dependencies:
!   basic_header_m         ETA0, FOURPI, RTOD, DTOR, constants
!   mesh_m                      MESH_TYPE (basis2, segs, nodes, Reflection_Coef)
!   nodes_wires_segments_m      SEGMENT_TYPE, NODE_TYPE
!   fresnel_reflection_m   cReal, cPerfect, cFreeSpace
!   matrix_m               MATRIX_TYPE (LU factorisation)
!   angle_cut_m            ANGLE_CUT_TYPE (spherical angle grid)
!   frequency_m            FREQUENCY_TYPE (bk, lambda, freq_mhz)
!   vector_and_utility_m   zp() (polar form), out(), CenteredOut(), toLower()
!   file_m                 FILE_TYPE, OpenFile(), copy_file()
!
!==============================================================================
!  SOLUTION FLOW
!==============================================================================
!
!  Typical main-program call sequence (single frequency):
!
!   call sys%Input()           1. read .geo file, build mesh, assemble Z, solve
!   call sys%pattern_3d(pat)   2. compute far-field on adaptive grid
!   call sys%data_out()        3. formatted panel + launch neomom_plot
!
!  Frequency sweep (nFreq > 1) — same sequence inside the freq loop in main.
!  Output files are automatically tagged with frequency:
!   Single : dipole.csv  dipole.txt  dipole.cur
!   Sweep  : dipole_7.000MHz.csv  dipole_7.000MHz.txt  dipole_7.000MHz.cur
!
!==============================================================================
!  COMMAND-LINE OPTIONS
!==============================================================================
!
!  argv(1)  : input .geo file path (required)
!  argv(2+) : optional key=value pairs (case-insensitive), any order
!
!  Supported keys:
!   plot=.false.         suppress neomom_plot launch (batch/sweep mode)
!   plot=.true.          force plot launch (default)
!   currents=.true.      override .nml output_currents — write .cur file
!   currents=.false.     override .nml output_currents — suppress .cur file
!   sweep=pattern        run full 3-D pattern (default)
!   sweep=vna_sweep      skip pattern_3d, write _Zin.csv only (VNA sweep)
!
!  Examples:
!   neomom dipole.nml
!   neomom dipole.nml plot=.false.
!   neomom dipole.nml plot=.false. currents=.true.
!   neomom dipole.nml sweep=vna_sweep
!   neomom dipole.nml sweep=vna_sweep plot=.false.
!
!  Notes:
!   - currents= and sweep= override their respective .nml settings unconditionally.
!     If absent, the .nml value is used unchanged.
!   - sweep_mode can also be set in &OPTIONS: sweep_mode = 'vna_sweep'
!   - Unknown keys produce a warning and are silently ignored.
!   - Values accept both .true./.false. and true/false (without dots).
!
!==============================================================================

   use basic_header_m
   use mesh_m
   use nodes_wires_segments_m
   use fresnel_reflection_m, only: cReal, cPerfect, cFreeSpace
   use matrix_m, only: MATRIX_TYPE
   use angle_cut_m
   use frequency_m
   use vector_and_utility_m
   use file_m

   implicit none; private

   public ANTENNA_TYPE

!------------------------------------------------------------------------------
!  PATTERN_TYPE: container for one 3-D far-field pattern result.
!
!  gainMax_db       -- peak G_total [dBi]
!  gainTheta_db     -- peak G_theta [dBi]; -100 used as sentinel for null polarisation
!  gainPhi_db       -- peak G_phi   [dBi]; -100 used as sentinel for null polarisation
!  gainMax          -- peak linear gain [−] (legacy, may be unused)
!  ang_of_max_gain  -- scalar angle of max gain (legacy, superseded by below)
!  AngleCut         -- full ANGLE_CUT_TYPE: angle grid, vK, uPol, nAng, etc.
!  Angle_maxGain(2,3) -- (dim,pol): dim=1→theta [deg], dim=2→phi [deg]
!                        pol=1→G_theta peak, pol=2→G_phi peak, pol=3→G_total peak
!  Etotal_abs(:)    -- |E_total| = sqrt(|E_theta|² + |E_phi|²) [V·m]
!                      stored before P_in normalisation; used by power_check.
!  P_rad            -- radiated power [W] from power_check integration; stored
!                      here so data_out can report the power balance.
!------------------------------------------------------------------------------
   type PATTERN_TYPE
      real                 :: gainMax_db = -100.0  ! peak G_total [dBi]
      real                 :: gainTheta_db = -100.0  ! peak G_theta [dBi]
      real                 :: gainPhi_db = -100.0  ! peak G_phi   [dBi]
      real                 :: gainMax, ang_of_max_gain
      type(ANGLE_CUT_TYPE) :: AngleCut
      real                 :: Angle_maxGain(2, 3)
      real, allocatable    :: Etotal_abs(:)
   end type PATTERN_TYPE

!------------------------------------------------------------------------------
!  ANTENNA_TYPE: top-level antenna object.
!
!  Integer counters:
!   nFreq            -- number of frequency points (currently 1)
!   nBasis           -- number of BASIS2_TYPE basis functions (set by mesh builder)
!   nSegments        -- number of segments (set by mesh builder)
!   nPort_Excitation -- number of voltage excitation ports
!   nBasisPerLambda  -- meshing density target (default 40 per wavelength)
!
!  Scalars:
!   PowerIn          -- total accepted power = sum of Pin across all ports [W]
!   P_rad            -- radiated power [W], set by power_check; used in data_out
!   SWR              -- primary-port SWR (port 1, 50 Ω reference)
!   heightAboveGround -- antenna base height above ground plane [m]
!   gamma            -- primary-port reflection coefficient Γ (port 1)
!   admittance       -- Y = 1/Z_in [S]  (computed in data_out)
!   inputImpedance   -- primary-port Z_in [Ω] (port 1)
!
!  Allocated arrays:
!   cur(:)           -- complex current coefficients, one per basis function [A or A/m]
!
!  Composite types:
!   mesh             -- MESH_TYPE: segs, nodes, basis2, Reflection_Coef, excitations
!   Freq             -- FREQUENCY_TYPE: bk, lambda, freq_mhz, cFreqUnits
!   Matrix           -- MATRIX_TYPE: LU-factored impedance matrix
!   Pat_3D           -- PATTERN_TYPE: 3-D pattern result (single frequency)
!
!  I/O:
!   cInFileBase      -- base name (without extension) of the input .geo file
!   cTitle           -- run title from /runTitle/ namelist
!   cVersion         -- version string embedded in output headers (default 'NeoMom v0')
!   GeoFile          -- FILE_TYPE for the .geo geometry input file
!   OutFile          -- FILE_TYPE for the .txt text output file
!                       Single freq: <cInFileBase>.txt (opened once in Input)
!                       Sweep:       <cInFileBase>_<freq>MHz.txt (reopened each freq)
!   OutFile_3d       -- FILE_TYPE for the .csv far-field pattern output file
!                       Single freq: <cInFileBase>.csv
!                       Sweep:       <cInFileBase>_<freq>MHz.csv
!
!  Command-line run control flags (set by Input arg parser):
!   bPlot        -- .TRUE. (default): launch neomom_plot after data_out
!                   .FALSE.: suppress plot launch (set by plot=.false.)
!   bCurrents    -- desired currents output state from command line
!                   Only meaningful when bCurrOverride = .TRUE.
!   bCurrOverride -- .TRUE. if currents= was present on command line.
!                    When .TRUE., bCurrents overrides mesh%bOutputCurrents
!                    unconditionally, ignoring the .nml output_currents value.
!                    When .FALSE., the .nml output_currents is used unchanged.
!
!  Sweep mode:
!   sweep_mode     -- 'pattern' (default) or 'vna_sweep'.
!                     Set via &OPTIONS sweep_mode or command-line sweep=.
!                     'pattern'   : full pattern_3d + data_out per frequency.
!                     'vna_sweep' : skip pattern_3d; write _Zin.csv row per freq.
!   bSweepOverride -- .TRUE. if sweep= was present on command line.
!                     When .TRUE., command-line sweep_mode wins over .nml value.
!------------------------------------------------------------------------------
   type ANTENNA_TYPE

      integer  :: nFreq = 1
      integer  :: nBasis
      integer  :: nSegments
      integer  :: nPort_Excitation
      integer  :: nBasisPerLambda = 40        ! meshing density target

      real(wp)        :: PowerIn               ! total accepted power [W]
      real(wp)        :: P_rad = ZERO       ! radiated power [W], set by power_check
      real(wp)        :: SWR                   ! primary-port SWR (port 1)
      real(wp)        :: heightAboveGround      ! [m];
      complex(wp)     :: gamma, admittance, inputImpedance

      complex(wp), allocatable :: cur(:)        ! current solution [A or A/m]

      type(MESH_TYPE)         :: mesh
      type(FREQUENCY_TYPE)    :: Freq
      type(MATRIX_TYPE)       :: Matrix
      type(PATTERN_TYPE)      :: Pat_3D         ! 3-D far-field result

      character(512)  :: cInFileBase            ! base filename (no extension)
      character(79)   :: cTitle                 ! run title from namelist
      character(40)   :: cVersion = 'NeoMom v0' ! version string for output headers

      type(FILE_TYPE) :: GeoFile                ! .geo  geometry input
      type(FILE_TYPE) :: OutFile                ! .txt  text summary output
      type(FILE_TYPE) :: OutFile_3d             ! .csv  pattern output

      ! ---- command-line run control flags ----
      logical :: bPlot = .TRUE.   ! .FALSE. suppresses neomom_plot launch
      logical :: bCurrents = .FALSE.  ! desired currents value from command line
      logical :: bCurrOverride = .FALSE.  ! .TRUE. if currents= was supplied on cmd line

      ! ---- sweep mode ----
      ! sweep_mode = 'pattern'   : full 3-D pattern + data_out (default)
      ! sweep_mode = 'vna_sweep' : Zin/SWR only, skip pattern_3d, write _Zin.csv
      ! Set via &OPTIONS sweep_mode = 'vna_sweep' in .nml, or
      ! command-line sweep=vna_sweep (command line wins when bSweepOverride=.TRUE.)
      character(20) :: sweep_mode = 'pattern'   ! 'pattern' or 'vna_sweep'
      logical       :: bSweepOverride = .FALSE.    ! .TRUE. if sweep= on command line

   contains

      procedure :: Input
      procedure :: pattern_3d
      procedure :: data_out
      procedure :: power_check

   end type ANTENNA_TYPE

contains

!==============================================================================
!  pattern_3d: compute and save the 3-D far-field pattern.
!
!  Callable as:  call sys%pattern_3d(sys%Pat_3D)
!
!  Steps:
!   1. Build adaptive angle grid (kD -> bw_deg -> Angle_del -> init_3D_pattern)
!   2. Call pattern_v2 to compute Er(nAng,2) [V*m]
!   3. Cache |Etot| in pat%Etotal_abs for power_check
!   4. Call power_check (sets this%P_rad and this%PowerIn via radiation integral)
!   5. Compute gain arrays G_theta, G_phi, G_total [linear]
!   6. Find peak gain and direction for each polarisation
!   7. Normalise Er: Er_out = Er / sqrt(P_in)   [V*m / W^0.5]
!   8. Write CSV file with embedded geometry metadata
!
!  Ordering constraint:
!   Steps 3-4 MUST precede step 5.  power_check reads pat%Etotal_abs and
!   writes this%PowerIn; the gain scale_G = FOURPI/(2*ETA0*PowerIn) requires
!   PowerIn to be set first.
!
!==============================================================================
!  GAIN DEFINITIONS
!==============================================================================
!
!  G_theta(iAng) = 4*pi * |Er(:,1)|^2 / (2*eta0 * P_in)   [linear]
!  G_phi  (iAng) = 4*pi * |Er(:,2)|^2 / (2*eta0 * P_in)
!  G_total(iAng) = G_theta + G_phi
!
!  Matches NEC2/EZNEC/FEKO/MMANA-GAL convention ("gain" = G_total by default).
!
!==============================================================================
!  ADAPTIVE ANGULAR GRID ALGORITHM
!==============================================================================
!
!  kD = bk * mesh%size                 (electrically-normalised antenna diameter)
!  bw_deg = min(360/kD, 50)            (estimated HPBW [deg], capped at 50°)
!  delta_raw = bw_deg / 10             (desired step: ~10 samples per beamwidth)
!  Angle_del = largest DIV360(i) <= delta_raw
!
!  DIV360(15) = [1,2,3,4,5,6,9,10,12,15,18,20,24,30,36]
!   Snapping to a divisor of 360 ensures the phi grid closes at exactly 360°
!   and the theta grid terminates at exactly 180° (or 90° with ground plane).
!
!==============================================================================
!  CSV OUTPUT FORMAT
!==============================================================================
!
!  Filename:
!   Single frequency : <cInFileBase>.csv
!   Sweep (nFreq>1)  : <cInFileBase>_<freq_mhz>MHz.csv  e.g. dipole_7.000MHz.csv
!
!  Header: version, timestamp, geometry file content (verbatim), then
!          filename, title, freq [MHz], wavelength [m], impedance, SWR,
!          peak gains [dBi] and angles, ground type, height, grid params.
!  Data: theta_deg  phi_deg  re_Etheta  im_Etheta  re_Ephi  im_Ephi
!   Field values are Er / sqrt(P_in) [V*m / W^0.5].
!   neomom_plot recovers gain as FOURPI/(2*ETA0) * |Er_norm|^2.
!
!==============================================================================
   subroutine pattern_3d(this, pat)

      use pattern_v2_m, only: pattern_v2

      class(ANTENNA_TYPE), intent(inout) :: this
      type(PATTERN_TYPE), intent(inout) :: pat

      ! Candidate angular step sizes: exact divisors of 360 (and 180)
      integer, parameter :: nDIV = 15
      integer, parameter :: DIV360(nDIV) = [1, 2, 3, 4, 5, 6, 9, 10, 12, 15, 18, 20, 24, 30, 36]

      complex, allocatable :: Er(:, :)      ! raw far-field [V*m], Er(nAng,2)
      real, allocatable :: G_theta(:)   ! gain arrays [linear]
      real, allocatable :: G_phi(:)
      real, allocatable :: G_total(:)

      integer  :: nAng, iAng, iU, iUgeo, iD
      real     :: kD, bw_deg, delta_raw, Angle_del
      real     :: scale_G                  ! = FOURPI / (2*ETA0 * P_in)
      integer  :: v(8)                     ! date_and_time values
      character(512) :: cLine

      real :: Gt_max, Gp_max, Gtot_max
      real :: Gt_theta, Gt_phi
      real :: Gp_theta, Gp_phi
      real :: Gtot_theta, Gtot_phi

      !--------| start |------------------------------------------------------

      associate (AngleCut => pat%AngleCut)

         ! ================================================================
         ! 1.  Angular grid
         ! ================================================================
         AngleCut%phi_min = 0.0; AngleCut%phi_max = 360.0

         ! Upper hemisphere only when ground plane is present
         if (this%mesh%Reflection_Coef%cGround_Plane == cFreeSpace) then
            AngleCut%theta_min = 0.0; AngleCut%theta_max = 180.0
         else
            AngleCut%theta_min = 0.0; AngleCut%theta_max = 90.0
         end if

         kD = this%freq%bk*this%mesh%size
         bw_deg = min(360.0/kD, 50.0)    ! cap at 50°: max step = 5°
         delta_raw = bw_deg/10.0

         Angle_del = 1.0                     ! floor: never coarser than 1°
         do iD = 1, nDIV
            if (real(DIV360(iD)) <= delta_raw) Angle_del = real(DIV360(iD))
         end do

         AngleCut%theta_del = Angle_del
         AngleCut%phi_del = Angle_del

         write (*, '(a,f7.2,a,f7.2,a,f5.1,a)') &
            '  Pattern grid: kD=', kD, '  BW=', bw_deg, 'deg  step=', Angle_del, 'deg'

         call pat%AngleCut%init_3D_pattern()
         nAng = AngleCut%nAng

         ! ================================================================
         ! 2.  Compute far-field Er(nAng,2)  [V*m]
         !     Er(:,1) = E_theta,  Er(:,2) = E_phi
         ! ================================================================
         call pattern_v2(this%mesh%basis2, this%mesh%segs, this%mesh%nodes, &
                         this%cur, this%freq%bk, AngleCut, &
                         this%mesh%Reflection_Coef, Er)

         ! ================================================================
         ! 3.  |E_total| for power_check  (must use raw, un-normalised Er)
         ! ================================================================
         if (allocated(pat%Etotal_abs)) deallocate (pat%Etotal_abs)
         allocate (pat%Etotal_abs(nAng))
         pat%Etotal_abs(:) = sqrt(abs(Er(:, 1))**2 + abs(Er(:, 2))**2)

         ! ================================================================
         ! 4.  Power check  (integrates |E|^2 over sphere; sets this%PowerIn
         !     and this%P_rad for the data_out panel)
         ! ================================================================
         call this%power_check()

         ! ================================================================
         ! 5.  Gain arrays  (computed BEFORE normalising Er in step 7)
         ! ================================================================
         allocate (G_theta(nAng), G_phi(nAng), G_total(nAng))

         scale_G = FOURPI/(2.0*ETA0*this%PowerIn)

         G_theta(:) = scale_G*abs(Er(:, 1))**2
         G_phi(:) = scale_G*abs(Er(:, 2))**2
         G_total(:) = G_theta(:) + G_phi(:)

         ! ================================================================
         ! 6.  Find peak gain direction for each polarisation
         ! ================================================================
         Gt_max = -huge(1.); Gp_max = -huge(1.); Gtot_max = -huge(1.)
         Gt_theta = 0.; Gt_phi = 0.
         Gp_theta = 0.; Gp_phi = 0.
         Gtot_theta = 0.; Gtot_phi = 0.

         do iAng = 1, nAng
            if (G_theta(iAng) > Gt_max) then
               Gt_max = G_theta(iAng)
               Gt_theta = AngleCut%angle_pairs(1, iAng)
               Gt_phi = AngleCut%angle_pairs(2, iAng)
            end if
            if (G_phi(iAng) > Gp_max) then
               Gp_max = G_phi(iAng)
               Gp_theta = AngleCut%angle_pairs(1, iAng)
               Gp_phi = AngleCut%angle_pairs(2, iAng)
            end if
            if (G_total(iAng) > Gtot_max) then
               Gtot_max = G_total(iAng)
               Gtot_theta = AngleCut%angle_pairs(1, iAng)
               Gtot_phi = AngleCut%angle_pairs(2, iAng)
            end if
         end do

         ! Store peak gains [dBi]; merge avoids log10(0) for null polarisation
         pat%gainMax_db = merge(10.*log10(Gtot_max), -100., Gtot_max > 0.)
         pat%gainTheta_db = merge(10.*log10(Gt_max), -100., Gt_max > 0.)
         pat%gainPhi_db = merge(10.*log10(Gp_max), -100., Gp_max > 0.)

         ! Angle_maxGain(dim, pol): dim=1->theta, dim=2->phi
         !                          pol=1->G_theta peak, 2->G_phi peak, 3->G_total peak
         pat%Angle_maxGain(1, 1) = Gt_theta; pat%Angle_maxGain(2, 1) = Gt_phi
         pat%Angle_maxGain(1, 2) = Gp_theta; pat%Angle_maxGain(2, 2) = Gp_phi
         pat%Angle_maxGain(1, 3) = Gtot_theta; pat%Angle_maxGain(2, 3) = Gtot_phi

         ! ================================================================
         ! 7.  Normalise Er for CSV output:  Er_out = Er / sqrt(P_in)
         !     plot_neomom recovers gain as FOURPI/(2*ETA0) * |Er_out|^2
         ! ================================================================
         Er(:, :) = Er(:, :)/sqrt(this%PowerIn)

         ! ================================================================
         ! 8.  Write CSV output file
         ! ================================================================
         ! ---- frequency-tagged CSV filename for sweep runs ----
         ! Single frequency : dipole.csv            (unchanged behaviour)
         ! Sweep (nFreq>1)  : dipole_7.000MHz.csv   (one file per frequency)
         if (this%freq%nFreq > 1) then
            write (this%OutFile_3d%cName, '(a,a,f0.3,a)') &
               trim(this%cInFileBase), '_', this%freq%freq_mhz, 'MHz.csv'
         else
            this%OutFile_3d%cName = trim(this%cInFileBase)//'.csv'
         end if

         open (newunit=iU, file=trim(this%OutFile_3d%cName), status='UNKNOWN')

         ! ---- embed geometry file verbatim as '#' header comments ----
         iUgeo = this%GeoFile%iU
         rewind (iUgeo)

         call date_and_time(values=v)   ! v: year,month,day,_,hour,min,sec,ms

         write (iU, '(a)') ' # '//trim(this%cVersion)
         write (iU, '(a,i4.4,2("-",i2.2),a,i2.2,2(":",i2.2))') &
            ' # ', v(1), v(2), v(3), ', T', v(5), v(6), v(7)
         write (iU, '(a)') '# '//trim(this%GeoFile%cName)

         do
            read (iUgeo, '(A)', end=899) cLine
            if (len_trim(cLine) /= 0) write (iU, '(a)') '# '//trim(cLine)
         end do
899      continue

901      format(A, A)

         write (iU, 901) '# '
         write (iU, 901) '# filename        : '//trim(this%OutFile_3d%cName)
         write (iU, 901) '# title           : '//trim(this%cTitle)
         write (iU, *) '# frequency_MHz   :', this%freq%freq_mhz
         write (iU, *) '# wavelength_m    :', this%freq%lambda
         write (iU, *) '#'
         write (iU, *) '# input impedance : ', this%inputImpedance
         write (iU, *) '# SWR             : ', this%SWR
         write (iU, *) '#'
         write (iU, *) '# gain_peak_dBi   : ', pat%gainMax_db
         write (iU, *) '# e_theta_max     : ', pat%Angle_maxGain(:, 1)
         write (iU, *) '# e_phi_max       : ', pat%Angle_maxGain(:, 2)
         write (iU, *) '# e_total_max     : ', pat%Angle_maxGain(:, 3)
         write (iU, *) '#'
         write (iU, *) '# ground_type     : ', this%mesh%Reflection_Coef%cGround_Plane
         write (iU, *) '# height above ground : ', this%heightAboveGround
         write (iU, *) '#'
         write (iU, *) '# theta_start     : ', AngleCut%theta_min
         write (iU, *) '# theta_stop      : ', AngleCut%Theta_max
         write (iU, *) '# theta_step      : ', AngleCut%theta_del
         write (iU, *) '# nTheta          : ', AngleCut%nTheta
         write (iU, *) '# phi_start       : ', AngleCut%phi_min
         write (iU, *) '# phi_stop        : ', AngleCut%phi_max
         write (iU, *) '# phi_step        : ', AngleCut%phi_del
         write (iU, *) '# nPhi            : ', AngleCut%nPhi
         write (iU, *) '#'
         write (iU, *) '# theta_deg, phi_deg, re_Etheta, im_Etheta, re_Ephi, im_Ephi'

         ! data rows (6 values; '(8g12.4)' has 2 extra slots — historical, harmless)
         do iAng = 1, nAng
            write (iU, '(8g12.4)') &
               AngleCut%thr(iAng)*RTOD, AngleCut%phr(iAng)*RTOD, &
               Er(iAng, 1), Er(iAng, 2)
         end do

         close (iU)
         write (*, '(a,a)') '  Pattern written: ', trim(this%OutFile_3d%cName)

      end associate

   end subroutine pattern_3d

!==============================================================================
!  power_check: verify energy conservation / measure radiation efficiency.
!
!  Callable as:  call this%power_check()
!  Called from:  pattern_3d (step 4), after pat%Etotal_abs is filled.
!
!  Reads:  this%Pat_3D%Etotal_abs(:)  [V*m, |r*E_total| far-field amplitude]
!          this%Pat_3D%AngleCut       [angle grid]
!          this%PowerIn               [W, feed accepted power]
!          this%mesh%Reflection_Coef%cGround_Plane
!
!  Writes: this%P_rad  [W] — stored for use by data_out panel
!          console report (solid angle fraction, P_rad, P_in, ratio, PASS/FAIL)
!
!==============================================================================
!  RADIATED POWER INTEGRAL
!==============================================================================
!
!  Time-averaged power density in the far field:
!   S(theta,phi) = |r*E_total|^2 / (2*eta0)   [W/sr]
!
!  Total radiated power:
!   P_rad = sum_iAng (1/2*ETA0) * Etotal(iAng)^2 * sin(thr) * dtheta * dphi
!
!==============================================================================
!  PHI TRAPEZOIDAL CORRECTION
!==============================================================================
!
!  init_3D_pattern runs phi from phi_min to phi_max INCLUSIVE, so for a
!  full azimuth sweep (0° to 360°) the first and last phi samples are at
!  the same physical direction (both 0°/360°).
!
!  Trapezoidal correction:
!   phiWeight = 0.5  for iPhi=1 (phi_min) and iPhi=nPhi (phi_max)
!   phiWeight = 1.0  for iPhi=2..nPhi-1 (interior)
!
!  Phi index within a theta row:
!   iPhi = mod(iAng - 1, AngleCut%nPhi) + 1
!
!==============================================================================
   subroutine power_check(this)

      class(ANTENNA_TYPE), intent(inout) :: this

      real    :: powerSum, SolidAngle_Total, solidAngle_ref
      real    :: thr, dtheta, dphi, dSolidAngle, dPower
      real    :: phiWeight, powerIn, ratio
      integer :: iAng, iPhi

      character(80) :: cGroundLabel

      !--------| start |------------------------------------------------------

      associate (AngleCut => this%pat_3d%AngleCut, &
                 Etotal => this%Pat_3D%Etotal_abs)

         powerSum = ZERO
         SolidAngle_Total = ZERO

         dtheta = AngleCut%theta_del*DTOR
         dphi = AngleCut%phi_del*DTOR

         do iAng = 1, AngleCut%nAng

            thr = AngleCut%thr(iAng)

            ! Phi index within this theta row: 1 = phi_min, nPhi = phi_max
            iPhi = mod(iAng - 1, AngleCut%nPhi) + 1

            ! Trapezoidal phi weight: halve endpoints to avoid double-counting
            phiWeight = ONE
            if (iPhi == 1 .or. iPhi == AngleCut%nPhi) phiWeight = HALF

            dSolidAngle = phiWeight*sin(thr)*dtheta*dphi
            SolidAngle_Total = SolidAngle_Total + dSolidAngle

            dPower = (HALF/ETA0)*Etotal(iAng)**2
            powerSum = powerSum + dPower*dSolidAngle

         end do

         ! Store radiated power for data_out panel
         this%P_rad = powerSum

         powerIn = this%PowerIn

         if (powerIn <= ZERO) then
            write (*, '(a)') '  power_check: WARNING — PowerIn <= 0, skipping ratio'
            ratio = ZERO
         else
            ratio = powerSum/powerIn
         end if

         if (this%mesh%Reflection_Coef%cGround_Plane == cFreeSpace) then
            solidAngle_ref = FOURPI
            cGroundLabel = 'Free space (full sphere)'
         else
            solidAngle_ref = TWOPI
            cGroundLabel = trim(this%mesh%Reflection_Coef%cGround_Plane)//' ground'
         end if

         write (*, '(a)') '  ===== Power Check ====='
         write (*, '(a,a)') '  Ground type       : ', trim(cGroundLabel)
         write (*, '(a,i7)') '  nAng              : ', AngleCut%nAng
         write (*, '(a,i4,a,i4)') '  (nTheta x nPhi)   : ', AngleCut%nTheta, ' x ', AngleCut%nPhi
         write (*, '(a,f10.6)') '  Solid angle/ref   : ', SolidAngle_Total/solidAngle_ref
         write (*, '(a,es13.5)') '  P_radiated  [W]   : ', powerSum
         write (*, '(a,es13.5)') '  P_input     [W]   : ', powerIn
         write (*, '(a,f10.6)') '  P_rad / P_in      : ', ratio

         select case (this%mesh%Reflection_Coef%cGround_Plane)
         case (cFreeSpace, cPerfect)
            if (abs(ratio - ONE) < 0.01) then
               write (*, '(a)') '  Result: PASS  (< 1% error)'
            else
               write (*, '(a,f6.1,a)') '  Result: FAIL  (', (ratio - ONE)*100., '% error)'
            end if
         case (cReal)
            write (*, '(a,f6.2,a)') '  Radiation efficiency: ', ratio*100., '%'
            if (ratio > ONE + 0.01) then
               write (*, '(a)') '  Result: FAIL  (ratio > 1 unphysical)'
            else
               write (*, '(a)') '  Result: OK    (efficiency measurement)'
            end if
         end select
         write (*, '(a)') '  ======================='

      end associate

   end subroutine power_check

!==============================================================================
!  data_out: formatted output panel + launch neomom_plot.
!
!  Writes a structured panel to both stdout and OutFile (.txt) covering:
!   Header         -- version, date/time, run title, input file
!   Frequency/mesh -- freq, lambda, nSegments, nBasis, segment length, kD
!   Ground         -- type; if REAL: epsilon_r, sigma, height
!   Per port       -- Zin (R+jX, |Z|∠θ), gamma, SWR, P_in  (one block per port)
!   Total power    -- sum of Pin across all ports
!   Pattern        -- theta/phi grid, peak G_total/G_theta/G_phi with angles
!   Power balance  -- P_rad, P_in, ratio; PASS/FAIL or efficiency %
!   Output files   -- .txt, .csv; .cur if currents were written
!
!  Preconditions:
!   pattern_3d must have been called (fills gainTheta_db, gainPhi_db,
!   Angle_maxGain, AngleCut, and OutFile_3d%cName).
!   power_check must have been called (fills this%P_rad).
!   Per-port compute_Zin_Pin and compute_gamma_SWR must have been called.
!
!  Output file naming:
!   Single frequency : dipole.txt, dipole.csv, dipole.cur
!   Sweep (nFreq>1)  : dipole_7.000MHz.txt, dipole_7.000MHz.csv, dipole_7.000MHz.cur
!   The .txt file is closed and reopened per frequency for sweep runs.
!   The .csv filename is set in pattern_3d before data_out is called.
!
!  Post-processing:
!   Launches neomom_plot via execute_command_line (non-blocking, wait=.false.)
!   unless bPlot = .FALSE. (set by plot=.false. on command line).
!==============================================================================
   subroutine data_out(this)

      use excitation_m, only: EXCITATION_TYPE

      class(ANTENNA_TYPE), intent(inout) :: this

      integer        :: iB, iUout, nPorts, i
      complex        :: zCur          ! polar form from zp(): (amplitude, phase_deg)
      real(wp)       :: zAng, gamAng, ratio
      character(256) :: cLine
      character(256) :: cName, cPlot
      integer        :: v(8)

      character(len=80), parameter :: SEP = &
                                      '================================================================================'
      character(len=80), parameter :: THIN = &
                                      '  ------------------------------------------------------------------------------'

      nPorts = size(this%mesh%excitations)
      call date_and_time(values=v)

      ! ---- frequency-tagged .txt summary for sweep runs ----
      ! Single frequency: dipole.txt (opened once in Input, reused here)
      ! Sweep (nFreq>1) : dipole_7.000MHz.txt (reopen per frequency)
      if (this%freq%nFreq > 1) then
         close (this%OutFile%iU)   ! close previous frequency's file
         write (this%OutFile%cName, '(a,a,f0.3,a)') &
            trim(this%cInFileBase), '_', this%freq%freq_mhz, 'MHz.txt'
         this%OutFile%cSTATUS = 'replace'
         call OpenFile(this%OutFile)
      end if

      ! Admittance (not stored per-port; computed here for primary port)
      this%admittance = zONE/this%inputImpedance

      ! ================================================================
      ! HEADER
      ! ================================================================
      call out(' ')
      call out(SEP)
      write (cLine, '(2x,a,t50,i4.4,2("-",i2.2),2x,i2.2,2(":",i2.2))') &
         trim(this%cVersion), v(1), v(2), v(3), v(5), v(6), v(7)
      call out(cLine)
      call out(SEP)
      write (cLine, '(2x,a,t12,a)') 'Run   :', trim(this%cTitle)
      call out(cLine)
      write (cLine, '(2x,a,t12,a)') 'File  :', trim(this%GeoFile%cName)
      call out(cLine)

      ! ================================================================
      ! FREQUENCY & MESH
      ! ================================================================
      call out(SEP)
      call out('  FREQUENCY & MESH')
      call out(THIN)
      write (cLine, '(2x,a,t26,a,f12.4,2x,a)') &
         'Frequency', ':', this%freq%freq_mhz, 'MHz'
      call out(cLine)
      write (cLine, '(2x,a,t26,a,f12.6,2x,a)') &
         'Wavelength', ':', this%freq%lambda, 'm'
      call out(cLine)
      write (cLine, '(2x,a,t26,a,i8)') &
         'Segments', ':', this%mesh%nSegs  !ments
      call out(cLine)
      write (cLine, '(2x,a,t26,a,i8)') &
         'Basis functions', ':', size(this%mesh%basis2)
      call out(cLine)
      write (cLine, '(2x,a,t26,a,f10.5,a,f6.1,a)') &
         'Segment length', ':', &
         this%freq%lambda/real(this%nBasisPerLambda, wp), &
         '  m   (lambda / ', real(this%nBasisPerLambda, wp), ')'
      call out(cLine)
      write (cLine, '(2x,a,t26,a,f10.4,a,f8.4,a)') &
         'Antenna size', ':', &
         this%mesh%size/this%freq%lambda, &
         '  lambda   (kD = ', this%freq%bk*this%mesh%size, ')'
      call out(cLine)

      ! ================================================================
      ! WIRE GEOMETRY
      ! ================================================================
      call out(SEP)
      call out('  WIRE GEOMETRY')
      call out(THIN)

      associate (wp2 => this%mesh%wire_primitives, &
                 np => this%mesh%node_primitives, &
                 cv => this%mesh%inputUnitsCv, &
                 cu => this%mesh%cInputUnits)

         ! ---- Node primitives — input units ----
         if (cv /= 1.0) then
            write (cLine, '(4x,a,t12,a,t26,a,t40,a)') &
               'Node', &
               'x ('//trim(cu)//')', 'y ('//trim(cu)//')', 'z ('//trim(cu)//')'
            call out(cLine)
            do i = 1, size(np)
               block
                  real :: vi(3)
                  vi = np(i)%v/cv
                  write (cLine, '(4x,a,t12,3f14.4)') &
                     trim(np(i)%tag), vi(1), vi(2), vi(3)
                  call out(cLine)
               end block
            end do
            call out(THIN)
         end if

         ! ---- Node primitives — metres ----
         write (cLine, '(4x,a,t12,a,t26,a,t40,a)') &
            'Node', 'x (m)', 'y (m)', 'z (m)'
         call out(cLine)
         do i = 1, size(np)
            write (cLine, '(4x,a,t12,3f14.4)') &
               trim(np(i)%tag), np(i)%v(1), np(i)%v(2), np(i)%v(3)
            call out(cLine)
         end do

         ! ---- Wire primitives ----
         ! Each wire shows: tag, node tags (one per line after first), radius
         call out(THIN)
         if (cv /= 1.0) then
            write (cLine, '(4x,a,t14,a,t24,a,t38,a,t52,a)') &
               'Wire', 'Node tags', 'Radius (m)', &
               'Length ('//trim(cu)//')', 'Length (lambda)'
         else
            write (cLine, '(4x,a,t14,a,t24,a,t38,a,t52,a)') &
               'Wire', 'Node tags', 'Radius (m)', &
               'Length (m)', 'Length (lambda)'
         end if
         call out(cLine)

         do iB = 1, size(wp2)
            associate (wire => wp2(iB))
               block
                  integer          :: j, kn
                  real             :: vm1(3), vm2(3), seg_m, total_m, total_u
                  character(len=8) :: tag1, tag2

                  ! Compute total wire length [m] by summing span lengths
                  total_m = 0.0
                  do j = 1, wire%nNodes - 1
                     tag1 = wire%nodeTags(j)
                     tag2 = wire%nodeTags(j + 1)
                     vm1 = 0.0; vm2 = 0.0
                     do kn = 1, size(np)
                        if (trim(np(kn)%tag) == trim(tag1)) vm1 = np(kn)%v
                        if (trim(np(kn)%tag) == trim(tag2)) vm2 = np(kn)%v
                     end do
                     seg_m = sqrt(sum((vm2 - vm1)**2))
                     total_m = total_m + seg_m
                  end do
                  total_u = total_m/cv   ! convert to input units

                  ! First line: wire tag, first node, radius, length, length/lambda
                  if (cv /= 1.0) then
                     write (cLine, '(4x,a,t14,a,t24,es12.5,2x,f12.4,2x,f10.5)') &
                        trim(wire%tag), trim(wire%nodeTags(1)), &
                        wire%radius, total_u, total_m/this%freq%lambda
                  else
                     write (cLine, '(4x,a,t14,a,t24,es12.5,2x,f12.4,2x,f10.5)') &
                        trim(wire%tag), trim(wire%nodeTags(1)), &
                        wire%radius, total_m, total_m/this%freq%lambda
                  end if
                  call out(cLine)

                  ! Remaining nodes indented below, no repeated length
                  do j = 2, wire%nNodes
                     write (cLine, '(4x,a,t14,a)') &
                        '', trim(wire%nodeTags(j))
                     call out(cLine)
                  end do
               end block
            end associate
         end do

      end associate

      ! ================================================================
      ! GROUND
      ! ================================================================
      call out(SEP)
      call out('  GROUND')
      call out(THIN)
      write (cLine, '(2x,a,t26,a,2x,a)') &
         'Type', ':', trim(this%mesh%Reflection_Coef%cGround_Plane)
      call out(cLine)
      if (this%mesh%Reflection_Coef%cGround_Plane == cReal) then
         write (cLine, '(4x,a,t26,a,f10.4)') &
            'Epsilon_r', ':', real(this%mesh%Reflection_Coef%epsilon_ground, wp)
         call out(cLine)
         write (cLine, '(4x,a,t26,a,es11.4,2x,a)') &
            'Sigma', ':', this%mesh%Reflection_Coef%sigma, 'S/m'
         call out(cLine)
         write (cLine, '(4x,a,t26,a,f10.4,2x,a)') &
            'Height above ground', ':', this%heightAboveGround, 'm'
         call out(cLine)
      end if

      ! ================================================================
      ! PER-PORT RESULTS  (one block per excitation)
      ! ================================================================
      do i = 1, nPorts

         associate (E => this%mesh%excitations(i))

            call out(SEP)
            write (cLine, '(2x,a,i2,a,i2,4x,a,a,a,t58,a,f7.2,a)') &
               'PORT ', i, ' of ', nPorts, &
               trim(E%cWireTag), ' / ', trim(E%cNodeTag), &
               'Z0_ref = ', E%Z0_ref, '  Ohm'
            call out(cLine)
            call out(THIN)

            zAng = atan2(aimag(E%Zin), real(E%Zin, wp))*RTOD

            write (cLine, '(2x,a,t26,a,f10.3,a,f10.3,2x,a)') &
               'Zin', ':', real(E%Zin, wp), '  +j ', aimag(E%Zin), 'Ohm'
            call out(cLine)
            write (cLine, '(2x,a,t26,a,f10.3,a,f8.2,a)') &
               '|Zin| / angle', ':', abs(E%Zin), '  Ohm  /  ', zAng, '  deg'
            call out(cLine)

            gamAng = atan2(aimag(E%gamma), real(E%gamma, wp))*RTOD

            write (cLine, '(2x,a,t26,a,f9.5,t54,a,f8.2,a)') &
               'Gamma', ':', abs(E%gamma), 'angle = ', gamAng, '  deg'
            call out(cLine)

            if (E%SWR >= huge(ONE)*0.5_wp) then
               write (cLine, '(2x,a,t26,a)') &
                  'SWR', ':  >> 1  (open / short circuit)'
            else
               write (cLine, '(2x,a,t26,a,f10.3)') 'SWR', ':', E%SWR
            end if
            call out(cLine)

            write (cLine, '(2x,a,t26,a,es11.4,a,f10.3,a)') &
               'P_in', ':', E%Pin, '  W     (', E%Pin*1000.0_wp, '  mW)'
            call out(cLine)

         end associate

      end do

      ! ================================================================
      ! TOTAL ACCEPTED POWER
      ! ================================================================
      call out(SEP)
      if (nPorts > 1) then
         write (cLine, '(2x,a,t26,a,es11.4,a)') &
            'TOTAL P_accepted', ':', this%PowerIn, '  W   (sum of all ports)'
      else
         write (cLine, '(2x,a,t26,a,es11.4,a)') &
            'P_accepted', ':', this%PowerIn, '  W'
      end if
      call out(cLine)

      ! ================================================================
      ! PATTERN
      ! ================================================================
      call out(SEP)
      call out('  PATTERN')
      call out(THIN)

      associate (AC => this%Pat_3D%AngleCut)
         write (cLine, '(2x,a,t10,a,f6.1,a,f6.1,a,f5.1,a,i5,a)') &
            'Theta', ':', AC%theta_min, ' to ', AC%theta_max, &
            ' deg   step ', AC%theta_del, ' deg  (', AC%nTheta, ' pts)'
         call out(cLine)
         write (cLine, '(2x,a,t10,a,f6.1,a,f6.1,a,f5.1,a,i5,a,i7,a)') &
            'Phi', ':', AC%phi_min, ' to ', AC%phi_max, &
            ' deg   step ', AC%phi_del, ' deg  (', AC%nPhi, &
            ' pts)   nAng = ', AC%nAng
         call out(cLine)
      end associate

      call out(THIN)

      write (cLine, '(2x,a,t26,a,f8.3,a,f7.2,a,f7.2,a)') &
         'Peak G_total', ':', this%Pat_3D%gainMax_db, &
         ' dBi   at  theta = ', this%Pat_3D%Angle_maxGain(1, 3), &
         ' deg   phi = ', this%Pat_3D%Angle_maxGain(2, 3), ' deg'
      call out(cLine)

      write (cLine, '(2x,a,t26,a,f8.3,a,f7.2,a,f7.2,a)') &
         'Peak G_theta', ':', this%Pat_3D%gainTheta_db, &
         ' dBi   at  theta = ', this%Pat_3D%Angle_maxGain(1, 1), &
         ' deg   phi = ', this%Pat_3D%Angle_maxGain(2, 1), ' deg'
      call out(cLine)

      if (this%Pat_3D%gainPhi_db > -99.0) then
         write (cLine, '(2x,a,t26,a,f8.3,a,f7.2,a,f7.2,a)') &
            'Peak G_phi', ':', this%Pat_3D%gainPhi_db, &
            ' dBi   at  theta = ', this%Pat_3D%Angle_maxGain(1, 2), &
            ' deg   phi = ', this%Pat_3D%Angle_maxGain(2, 2), ' deg'
      else
         write (cLine, '(2x,a,t26,a)') &
            'Peak G_phi', ':  (null — E_phi identically zero)'
      end if
      call out(cLine)

      ! ================================================================
      ! POWER BALANCE
      ! ================================================================
      call out(SEP)
      write (cLine, '(2x,a,2x,a)') 'POWER BALANCE', &
         '('//trim(this%mesh%Reflection_Coef%cGround_Plane)//')'
      call out(cLine)
      call out(THIN)

      write (cLine, '(2x,a,t26,a,es11.4,2x,a)') &
         'P_radiated', ':', this%P_rad, 'W'
      call out(cLine)
      write (cLine, '(2x,a,t26,a,es11.4,2x,a)') &
         'P_accepted', ':', this%PowerIn, 'W'
      call out(cLine)

      if (this%PowerIn > ZERO) then
         ratio = this%P_rad/this%PowerIn
         select case (this%mesh%Reflection_Coef%cGround_Plane)
         case (cFreeSpace, cPerfect)
            if (abs(ratio - ONE) < 0.01_wp) then
               write (cLine, '(2x,a,t26,a,f9.4,t50,a)') &
                  'Ratio P_rad/P_in', ':', ratio, 'PASS  (< 1% error)'
            else
               write (cLine, '(2x,a,t26,a,f9.4,t50,a,f6.1,a)') &
                  'Ratio P_rad/P_in', ':', ratio, 'FAIL  (', (ratio - ONE)*100., '% error)'
            end if
            call out(cLine)
         case (cReal)
            write (cLine, '(2x,a,t26,a,f9.4,t50,a,f5.1,a)') &
               'Radiation efficiency', ':', ratio, '(', ratio*100., '%)'
            call out(cLine)
         end select
      end if

      ! ================================================================
      ! OUTPUT FILES
      ! ================================================================
      call out(SEP)
      call out('  OUTPUT FILES')
      call out(THIN)
      write (cLine, '(2x,a,t26,a,2x,a)') 'Text summary', ':', trim(this%OutFile%cName)
      call out(cLine)
      write (cLine, '(2x,a,t26,a,2x,a)') 'Pattern CSV', ':', trim(this%OutFile_3d%cName)
      call out(cLine)

      ! ---- optional current file (.cur) ----
      if (this%mesh%bOutputCurrents) then

         ! Frequency-tagged on sweeps, plain name for single frequency
         if (this%freq%nFreq > 1) then
            write (cName, '(a,a,f0.3,a)') &
               trim(this%cInFileBase), '_', this%freq%freq_mhz, 'MHz.cur'
         else
            cName = trim(this%cInFileBase)//'.cur'
         end if

         open (newUnit=iUout, File=trim(cName))
         ! Columns: iBasis, vNode(3), Re(I), Im(I), |I| [mA], phase [deg]
         do iB = 1, size(this%cur)
            zCur = zp(this%cur(iB))
            write (iUout, '(i5,3g13.5,2g13.5,2g13.5)') iB, &
               this%mesh%basis2(iB)%vNode, &
               real(this%cur(iB)), aimag(this%cur(iB)), &
               real(zCur), aimag(zCur)
         end do
         close (iUout)
         write (cLine, '(2x,a,t26,a,2x,a)') 'Current file', ':', trim(cName)
         call out(cLine)
      end if

      call out(SEP)
      call out('')

      ! ---- launch Python post-processor (non-blocking) ----
      if (this%bPlot) then
         cPlot = 'neomom_plot  '
         call execute_command_line(trim(cPlot)//'  '//trim(this%OutFile_3d%cName), &
                                   wait=.false.)
      else
         write (*, '(2x,a)') 'Plot suppressed (plot=.false. on command line)'
      end if

   end subroutine data_out

!==============================================================================
!  Input: read the .geo file, build the mesh, fill and factor the Z-matrix.
!         Also parses optional command-line key=value flags (argv 2..N).
!
!  Called as:  call sys%Input()
!  Arguments:  none (all state goes into this%...)
!
!  Command-line parsing (argv 2..N, after the mandatory .geo filename):
!   Key=value pairs are matched case-insensitively using toLower().
!   Supported keys: plot, currents  (see module header for full details).
!   Unknown keys produce a WARNING to stdout and are ignored.
!   Parsed values are echoed to stdout for traceability in batch logs.
!
!==============================================================================
!  .GEO FILE STRUCTURE (Fortran NAMELIST format)
!==============================================================================
!
!  &runTitle  title = "my antenna"  /
!
!  &Frequency  ... /        (read by frequency_m::Read_Freq_Data)
!
!  &Ground
!    Ground_Plane = 'FREE_SPACE'   ! or 'PERFECT' or 'REAL'
!    epsilon      = 14.0           ! relative permittivity (real part)
!    sigma        = 0.005          ! conductivity [S/m]
!  /
!
!  &OPTIONS
!    nBasisPerLambda  = 40           ! mesh density
!    output_currents  = .FALSE.      ! write .cur file
!    sweep_mode       = 'pattern'    ! 'pattern' or 'vna_sweep'
!  /
!
!  Node/wire primitives in geometry-specific format (read_geometry_input).
!  Excitation specification (read_excitations).
!
!==============================================================================
!  READ SEQUENCE
!==============================================================================
!
!  1. /runTitle/     → this%cTitle
!  2. Freq%Read_Freq_Data → this%freq (bk, lambda, freq_mhz, ...)
!     Freq%Freq_Set(1)    → selects first frequency point
!  3. /Ground/       → Reflection_Coef%cGround_Plane, epsilon_ground, sigma
!  4. /OPTIONS/      → nBasisPerLambda, mesh%bOutputCurrents
!                    If currents= was on command line, bCurrOverride overrides
!                    mesh%bOutputCurrents after the namelist read.
!  5. read_geometry_input → mesh%node_primitives, wire_primitives, zHeight
!  6. read_excitations    → mesh%excitations
!
!  NOTE: There is a potential type mismatch in step 3.  The local variable
!   `epsilon` is declared real(wp), but on line 849 it is initialized from
!   `this%mesh%Reflection_Coef%epsilon` which is complex (the frequency-
!   dependent value).  Most compilers will silently take the real part;
!   the intended default is the real εr stored in epsilon_ground, not the
!   complex computed epsilon.  The initialization should be:
!     epsilon = real(this%mesh%Reflection_Coef%epsilon_ground)
!
!==============================================================================
   subroutine Input(this)

      use excitation_m

      class(ANTENNA_TYPE), target, intent(inout) :: this

      integer         :: nArg, l, iErr, ios !, i
      character(198)  :: cBuffer
      integer         :: nBasisPerLambda
      character       :: cInFileBase*256, msg*200
      real(wp)        :: epsilon = 14.0, sigma = 0.005, segment_length_desired
      character(10)   :: Ground_Plane
      character(80)   :: title
      !character(8)    :: NodeTag
      ! character(16)   :: WireTag
      logical         :: output_currents
      character(20)   :: sweep_mode
      real            :: zHeight

      ! ---- explicit defaults (avoid implied SAVE from declaration init) ----
      output_currents = .FALSE.
      sweep_mode = 'pattern'

      NAMELIST /OPTIONS/ nBasisPerLambda, output_currents, sweep_mode
      namelist /ground/ Ground_Plane, epsilon, sigma
      namelist /runTitle/ title

      !------------------------| start |----------------------------------------

      nBasisPerLambda = this%nBasisPerLambda

      nArg = COMMAND_ARGUMENT_COUNT()

      if (nArg == 0) then
         call out("Usage: NEO WIRE MOM requires the input file on the command line")
         call fatalStop()
      end if

      call Get_Command_Argument(0, cBuffer)
      call Get_Command_Argument(1, this%GeoFile%cName)

      ! ---- optional key=value arguments (argv 2..N) ----------------------
      ! Usage examples:
      !   neomom input.nml plot=.false.
      !   neomom input.nml currents=.true.
      !   neomom input.nml plot=.false. currents=.true.
      ! Keys are case-insensitive. Values accept .true./.false. or true/false.
      ! Unknown keys produce a warning and are ignored.
      block
         integer        :: iArg, ieq
         character(256) :: cArg, cKey, cVal

         do iArg = 2, nArg
            call Get_Command_Argument(iArg, cArg)
            cArg = trim(adjustl(cArg))
            ieq = index(cArg, "=")

            if (ieq > 0) then
               cKey = cArg(1:ieq - 1)
               cVal = cArg(ieq + 1:)
               call toLower(cKey)
               call toLower(cVal)

               select case (trim(cKey))

               case ("plot")
                  this%bPlot = (trim(cVal) == ".true." .or. trim(cVal) == "true")
                  write (*, "(2x,a,l1)") "Command-line: plot     = ", this%bPlot

               case ("currents")
                  this%bCurrents = (trim(cVal) == ".true." .or. trim(cVal) == "true")
                  this%bCurrOverride = .TRUE.   ! flag that cmd-line wins over .nml
                  write (*, "(2x,a,l1)") "Command-line: currents = ", this%bCurrents

               case ("sweep")
                  ! Accepted values: pattern, vna_sweep
                  ! Command-line always wins over .nml sweep_mode
                  this%sweep_mode = trim(cVal)
                  this%bSweepOverride = .TRUE.
                  write (*, "(2x,a,a)") "Command-line: sweep    = ", trim(this%sweep_mode)

               case default
                  write (*, "(2x,a,a,a)") &
                     "WARNING: unknown command-line option ", trim(cArg), " ignored"

               end select
            end if
         end do
      end block
      ! ---------------------------------------------------------------------

      this%GeoFile%cName = trim(this%GeoFile%cName)

      l = len(trim(this%GeoFile%cName))
      this%cInFileBase = this%GeoFile%cName(1:l - 4)    ! strip trailing '.geo'

      cInFileBase = this%cInFileBase

      this%OutFile%cName = trim(cInFileBase)//'.txt'

      this%OutFile%cSTATUS = 'replace'
      call OpenFile(this%OutFile)
      iFileOut = this%OutFile%iU

      write (*, *)
      write (*, *) 'Opening and Reading Input Geometry File : '
      write (*, *) '     ', trim(this%GeoFile%cName)
      write (*, *)

      call OpenFile(this%GeoFile, cSTATUS=cSTATUS_OLD)

      associate (iGeo => this%GeoFile%iU)

         rewind (iGeo)

         call copy_file(iGeo, iuOut=6)
         call copy_file(iGeo, iFileOut)

         ! ---- 1. Run title ----
         rewind (iGeo)
         read (iGeo, NML=runTitle, IOSTAT=ios, iomsg=msg)
         write (*, nml=runTitle)
         call nml_error('runTitle', ios, msg)
         this%cTitle = title

         ! ---- 2. Frequency ----
         call this%Freq%Read_Freq_Data(iGeo)
         call this%freq%Freq_Set(1)

         ! ---- 3. Ground plane ----
         Ground_Plane = this%mesh%Reflection_Coef%cGround_Plane
         ! NOTE: epsilon should default from epsilon_ground (real), not
         !       epsilon (complex); see note in subroutine header above.
         epsilon = this%mesh%Reflection_Coef%epsilon    ! potential type mismatch
         sigma = this%mesh%Reflection_Coef%sigma

         rewind (iGeo)
         read (iGeo, NML=Ground, IOSTAT=ios, iomsg=msg)
         write (*, nml=ground)
         call nml_error('Ground', ios, msg)

         call toUpper(Ground_Plane)

         this%mesh%Reflection_Coef%cGround_Plane = Ground_Plane
         this%mesh%Reflection_Coef%epsilon_ground = epsilon
         this%mesh%Reflection_Coef%sigma = sigma

         ! ---- 4. Options ----
         rewind (iGeo)
         read (iGeo, NML=OPTIONS, IOSTAT=iErr)
         if (iErr /= 0) then
            write (this%OutFile%iU, *)
            call CenteredOut('---| Name List Data Defaults |---')
            write (this%OutFile%iU, *)
            write (this%OutFile%iU, NML=OPTIONS)
            write (*, nml=OPTIONS)
            call FatalError('Error in OPTIONS name list', 'iErr', iErr)
         end if

         this%nBasisPerLambda = nBasisPerLambda
         this%mesh%bOutputCurrents = output_currents

         ! Command-line currents= overrides the .nml setting unconditionally.
         ! If currents= was supplied on the command line, bCurrOverride is .TRUE.
         ! and bCurrents holds the desired value regardless of .nml.
         if (this%bCurrOverride) this%mesh%bOutputCurrents = this%bCurrents

         ! Apply sweep_mode from .nml — command-line sweep= wins if supplied.
         ! bSweepOverride is .TRUE. only when sweep= appears on the command line.
         if (.not. this%bSweepOverride) this%sweep_mode = trim(sweep_mode)

         write (this%OutFile%iU, *)
         call CenteredOut('---| Name List Data |---')
         write (this%OutFile%iU, *)
         write (this%OutFile%iU, NML=OPTIONS)
         write (*, NML=OPTIONS)

         segment_length_desired = this%freq%lambda/real(nBasisPerLambda)

         ! ---- 5. Node and wire primitives ----
         call read_geometry_input(iGeo, this%mesh%node_primitives, &
                                  this%mesh%wire_primitives, zHeight, &
                                  this%mesh%cInputUnits, this%mesh%inputUnitsCv)

         this%heightAboveGround = zHeight   ! [sic] typo in field name

         ! ---- 6. Excitation ports ----
         rewind (iGeo)
         call read_excitations(iGeo, this%mesh%excitations)

      end associate

   end subroutine Input

end module antenna_system_m
