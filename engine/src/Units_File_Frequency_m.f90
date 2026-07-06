!==============================================================================
!  Units_File_Frequency_m.f90
!
!  Three support modules included by the NeoMoM geometry and solver layers:
!
!   units_m     -- geometry coordinate units and meters conversion factor
!   file_m      -- FILE_TYPE wrapper for Fortran open/close/delete
!   frequency_m -- frequency list, current wave number bk, and lambda
!
!  All three are legacy-compatible: public names and call patterns are unchanged.
!==============================================================================

!==============================================================================
Module units_m
!
!  Purpose:
!   Encapsulates the input geometry coordinate unit system and the
!   corresponding conversion factor to meters (unitsCv).  All wire
!   node coordinates read from the .nml input file are multiplied by
!   unitsCv before being stored so that the rest of NeoMoM works
!   exclusively in SI meters.
!
!  Supported unit strings (case-insensitive, matched on first character
!  with 'M'/'m' disambiguated by the second character):
!
!   "METERS"  / "M"  -> unitsCv = 1.0      (no conversion needed)
!   "MM"             -> unitsCv = 0.001     (millimetres to metres)
!   "CM"      / "C"  -> unitsCv = 0.01      (centimetres to metres)
!   "INCHES"  / "I"  -> unitsCv = 0.0254
!   "FEET"    / "F"  -> unitsCv = 0.3048
!   "NONE"    / "N"  -> unitsCv = 1.0      (dimensionless, no conversion)
!   "LAMBDA"  / "L"  -> unitsCv = 1.0      (wavelength-normalised;
!                                            caller must scale by lambda)
!
!  Note on LAMBDA: unitsCv = 1.0 because the conversion from
!  wavelength-normalised coordinates to meters requires the wavelength,
!  which is not known at unit-initialisation time.  Callers that use
!  LAMBDA units must apply the additional factor (lambda_metres) themselves
!  after Freq_Set() has set the current wavelength.
!==============================================================================

   use basic_header_m
   use vector_and_utility_m

   implicit none
   private

   public  :: UNITS_TYPE

   integer, parameter :: nCharLen = 20

   !  Internal string tokens for unit names.
   character(nCharLen), parameter :: &
      cMETERS = 'METERS' &
      , cCM = 'CM' &
      , cMM = 'MM' &
      , cINCHES = 'INCHES' &
      , cFEET = 'FEET' &
      , cNONE = 'NONE' &
      , cLAMBDA = 'LAMBDA'

   character(nCharLen) ::  cUNITS = cMETERS    ! module-level default (not exposed)

!------------------------------------------------------------------------------
!  UNITS_TYPE
!
!   cInputUnits  : unit string as read from the input file (e.g., 'MM', 'FEET')
!   cUnits       : normalised canonical name (e.g., cMM, cFEET)
!   unitsCv      : multiply raw input coordinates by this to get metres.
!                  = 1.0 for METERS, NONE, and LAMBDA.
!------------------------------------------------------------------------------
   type UNITS_TYPE
      character(nCharLen) :: cUnits = cNONE  ! canonical unit name
      character(nCharLen) :: cInputUnits = cNONE  ! raw string from input
      real(wp)            :: unitsCv = 1.0    ! conversion factor to metres
   contains
      procedure :: init        ! initialise from a unit string (programmatic)
      procedure Read_Input     ! read unit string from open file (input-deck path)
   end type Units_Type

contains

!------------------------------------------------------------------------------
!  init: set unit fields from a caller-supplied string cInputUnits.
!  Matching is on the first character only, except 'M'/'m' which requires
!  the second character to distinguish METERS (default) from MM.
!  Fatal error if the unit string is not recognised.
!------------------------------------------------------------------------------
   subroutine init(U, cInputUnits)
      class(Units_Type), intent(inout) :: U
      character(*), intent(in)    :: cInputUnits

      U%cInputUnits = cInputUnits

      select case (adjustl(U%cInputUnits(1:1)))
      case ('M', 'm')
         select case (U%cInputUnits(2:2))
         case ('M', 'm'); U%cUNITS = cMM; U%unitsCv = 0.001   ! "MM"
         case default; U%cUNITS = cMETERS; U%unitsCv = 1.0     ! "M", "METERS"
         end select
      case ('C', 'c'); U%cUNITS = cCM; U%unitsCv = 0.01
      case ('F', 'f'); U%cUNITS = cFEET; U%unitsCv = 0.3048
      case ('I', 'i'); U%cUNITS = cINCHES; U%unitsCv = 0.0254
      case ('N', 'n'); U%cUNITS = cNONE; U%unitsCv = 1.0
      case ('L', 'l'); U%cUNITS = cLAMBDA; U%unitsCv = 1.0       ! see module note
      case default; call FatalError('SetUnits: cInputUnits not Recognized', '', 0)
      end select

   end subroutine init

!------------------------------------------------------------------------------
!  Read_Input: read the keyword "wire_Units" from the open file unit iU and
!  initialise U accordingly.  Uses char_value_after_equal from
!  vector_and_utility_m to parse the "wire_Units = <value>" line.
!
!  Note: the unit-selection logic here duplicates init() above.  A future
!  refactor could call init() after reading cInputUnits, but the current
!  form is intentionally left as-is for compatibility.
!------------------------------------------------------------------------------
   subroutine Read_Input(U, iU)
      Class(Units_Type)        :: U
      integer, intent(in) :: iU
      integer      :: iErr
      logical      :: bErr

      U%cInputUnits = char_value_after_equal('wire_Units', iU, bErr)
      if (bErr) call FatalError('input units not found', 'iErr', iErr)

      select case (adjustl(U%cInputUnits(1:1)))
      case ('M', 'm')
         select case (U%cInputUnits(2:2))
         case ('M', 'm'); U%cUNITS = cMM; U%unitsCv = 0.001
         case default; U%cUNITS = cMETERS; U%unitsCv = 1.0
         end select
      case ('C', 'c'); U%cUNITS = cCM; U%unitsCv = 0.01
      case ('F', 'f'); U%cUNITS = cFEET; U%unitsCv = 0.3048
      case ('I', 'i'); U%cUNITS = cINCHES; U%unitsCv = 0.0254
      case ('N', 'n'); U%cUNITS = cNONE; U%unitsCv = 1.0
      case ('L', 'l'); U%cUNITS = cLAMBDA; U%unitsCv = 1.0
      case default; call FatalError('SetUnits: cInputUnits not Recognized', '', 0)
      end select

   end subroutine Read_Input

end module units_m

!==============================================================================
Module file_m
!
!  Purpose:
!   Provides FILE_TYPE, a thin object-oriented wrapper around the Fortran
!   OPEN/CLOSE/INQUIRE statements.  Encapsulates the file name, access
!   attributes, and the Fortran I/O unit number (iU) so callers do not
!   manage units manually.
!
!  Sentinel convention:
!   FILE_TYPE%iU = 0 means the file is not currently open.
!   NEWUNIT always returns a compiler-assigned positive value, so 0 is
!   a safe "not open" sentinel that never conflicts with a real unit.
!
!  String constants (all public):
!   cSTATUS_*  : STATUS= specifier values for OPEN
!   cFORM_*    : FORM= specifier values
!   cACCESS_*  : ACCESS= specifier values
!   cACTION_*  : ACTION= specifier values
!   cPosition_default : POSITION='ASIS' (leave file pointer where it is)
!==============================================================================

   use basic_header_m
   implicit none; private

   public FILE_TYPE, OpenFile

   !  String tokens for Fortran OPEN specifiers, exposed as public constants
   !  so callers can use them without hard-coding string literals.
   character(*), parameter, public :: &
      cSTATUS_OLD = 'OLD' &  ! file must pre-exist
      , cSTATUS_NEW = 'NEW' &  ! file must not pre-exist
      , cSTATUS_SCRATCH = 'SCRATCH' &  ! temporary file, deleted on close
      , cSTATUS_UNKNOWN = 'UNKNOWN' &  ! open whether or not file exists
      , cSTATUS_REPLACE = 'REPLACE' &  ! create or overwrite
      , cFORM_BINARY = 'BINARY' &  ! Intel-extension binary stream
      , cFORM_FORMATTED = 'FORMATTED' &  ! human-readable text (default)
      , cFORM_UNFORMATTED = 'UNFORMATTED' &  ! raw binary (standard)
      , cACCESS_Direct = 'DIRECT' &  ! fixed-length record direct access
      , cACCESS_STREAM = 'STREAM' &  ! Fortran 2003 stream access
      , cACCESS_SEQUENTIAL = 'SEQUENTIAL' & ! record-by-record (default)
      , cACTION_READ = 'READ' &
      , cACTION_WRITE = 'WRITE' &
      , cACTION_READWRITE = 'READWRITE' &
      , cPosition_default = 'ASIS'          ! do not rewind on open

!------------------------------------------------------------------------------
!  FILE_TYPE
!
!   cName    : file path/name (must be set by caller before calling Open)
!   cFORM    : FORM=  (default FORMATTED)
!   cSTATUS  : STATUS= (default REPLACE -- create or overwrite)
!   cACCESS  : ACCESS= (default SEQUENTIAL)
!   cACTION  : ACTION= (default READWRITE)
!   cPosition: POSITION= (default ASIS)
!   iU       : Fortran I/O unit, assigned by NEWUNIT on open.
!              0 = not open.
!------------------------------------------------------------------------------
   type FILE_TYPE
      character(MAXNAME) :: cName
      character(20)      :: cFORM = cFORM_FORMATTED
      character(20)      :: cSTATUS = cSTATUS_REPLACE
      character(20)      :: cACCESS = cACCESS_SEQUENTIAL
      character(20)      :: cACTION = cACTION_READWRITE
      character(20)      :: cPosition = cPosition_default
      integer            :: iU = 0                  ! 0 = not open
   contains
      procedure Open
      procedure Close
      procedure Delete_file
   end type

contains

!------------------------------------------------------------------------------
!  delete_file: close and delete the file.
!  Handles three cases: file does not exist (no-op), file exists and is open,
!  file exists but is not currently open (opens it first to get a unit).
!------------------------------------------------------------------------------
   subroutine delete_file(this)
      class(FILE_TYPE) :: this
      integer:: stat, iU
      logical :: exists

      inquire (file=trim(this%cName), number=iU, exist=exists)
      if (exists) then
         if (iU == -1) then  ! exists on disk but no unit is attached -- open to get one
            open (file=trim(this%cName), newunit=iU, iostat=stat)
         end if
         close (iU, status="delete", iostat=stat)
         this%iU = 0
      end if
   end subroutine delete_file

!------------------------------------------------------------------------------
!  close: close the file and reset iU to 0 (sentinel for not open).
!------------------------------------------------------------------------------
   subroutine close (file)
      class(FILE_TYPE) :: file
      close (file%iu)
      file%iu = 0
   end subroutine close

!------------------------------------------------------------------------------
!  open: type-bound open with optional attribute overrides.
!  All optional arguments default to the type defaults defined above.
!
!  Guard: if iU /= 0 the file is already open -- silently set STATUS='OLD'
!  and return.  This prevents double-open errors in code paths that call
!  open() redundantly.
!
!  SCRATCH files are opened without a file name (Fortran standard).
!  All other cases use NEWUNIT to get a compiler-assigned unit number.
!------------------------------------------------------------------------------
   subroutine open (file, FORM, STATUS, ACTION, Position, Access)
      class(FILE_TYPE) :: file
      character(*), optional, intent(in) :: FORM, STATUS, ACTION, Position, Access

      integer        :: iErr, iU
      character(200) :: cMsg = ' '

      if (file%iU /= 0) then   ! already open -- do not re-open
         file%cSTATUS = 'OLD'
         return
      end if

      ! Reset to defaults before applying any caller overrides
      file%cSTATUS = cSTATUS_REPLACE
      file%cFORM = cFORM_FORMATTED
      file%cACTION = cACTION_READWRITE
      file%cPosition = cPosition_default

      if (present(FORM)) file%cFORM = FORM
      if (present(STATUS)) file%cSTATUS = STATUS
      if (present(ACTION)) file%cACTION = ACTION
      if (present(Position)) file%cPosition = Position
      if (present(Access)) file%cAccess = Access

      select case (file%cSTATUS)
      case (cSTATUS_SCRATCH)
         ! SCRATCH: no file name; compiler assigns and deletes on close
         open (NEWUNIT=iU, action=trim(file%cAction), access=trim(file%cAccess), &
               form=trim(file%cForm), status=cStatus_Scratch, &
               position=trim(file%cPosition), iostat=iErr, iomsg=cMsg)
      case default
         open (NEWUNIT=iU, file=trim(file%cName), action=trim(file%cAction), &
               access=trim(file%cAccess), form=trim(file%cForm), &
               status=trim(file%cSTATUS), position=trim(file%cPosition), &
               iostat=iErr, iomsg=cMsg)
      end select

      file%iU = iU

      if (iErr /= 0) call fatalError('file_m::Open failed', file%cName//' iErr', iErr)

   end subroutine open

!------------------------------------------------------------------------------
!  OpenFile: standalone (non-type-bound) convenience wrapper.
!  Simpler interface than the type-bound open(): only FORM and STATUS are
!  overridable.  Always rewinds after opening (unlike the type-bound open()).
!  Closes any previously open unit on this FILE_TYPE before re-opening.
!------------------------------------------------------------------------------
   subroutine openFile(file, cFORM, cSTATUS)
      type(file_type), intent(inout) :: file
      character(*), optional, intent(in) :: cSTATUS, cForm

      character(200)  :: cMsg
      integer :: iErr

      if (file%iU > 0) close (file%iU)   ! close if already open

      if (present(cFORM)) file%cFORM = cFORM
      if (present(cSTATUS)) file%cSTATUS = cSTATUS

      !open (NEWUNIT=fileIN%iU, file=trim(fileIN%cName), status='UNKNOWN', &
      !      iostat=iErr, iomsg=cMsg)

      open (NEWUNIT=file%iU, file=trim(file%cName), form=trim(file%cForm), &
            status=trim(file%cSTATUS), iostat=iErr, iomsg=cMsg)

      if (iErr /= 0) call fatalError(trim(cmsg), file%cName//' iErr', iErr)

      rewind (file%iU)
   end subroutine openFile

end module file_m

!==============================================================================
Module frequency_m
!
!  Purpose:
!   Manages the frequency sweep list and the current-frequency state
!   variables consumed by the NeoMoM solver:
!
!     bk     = free-space wave number k = 2*pi*f/c = 2*pi/lambda  [1/m]
!     lambda = free-space wavelength  [m]
!     freq   = current frequency      [Hz]  (always stored in Hz internally)
!
!  bk is the quantity used directly in every EFIE integral:
!    - Z_mn prefactor:   j*k*ETA0 / (4*pi)
!    - Green's function: exp(-j*k*R) / R
!    - Pattern prefactor: -j*k*ETA0 / (4*pi)
!  Setting the correct bk via Freq_Set() is therefore the essential
!  step before any matrix fill or pattern computation.
!
!  Supported frequency units:
!    cMHZ    = 'MHz'    -- input array in megahertz  (most common HF/VHF case)
!    cGHZ    = 'GHz'    -- input array in gigahertz
!    cLAMBDA = 'LAMBDA' -- input "frequency" is actually wavelength in metres;
!                          bk = 2*pi/lambda_input, freq derived from c/lambda
!
!  Current limitation:
!    Read_Freq_Data reads only the &Frequency_MHz namelist group.
!    GHz and LAMBDA sweeps must be set programmatically via init().
!==============================================================================

   use basic_header_m
   implicit none
   private

   public FREQUENCY_TYPE

   integer, parameter  :: nCharLen = 20

   character(20), parameter :: &
      cGHZ = 'GHz' &
      , cMHZ = 'MHz' &
      , cLAMBDA = 'LAMBDA'

!------------------------------------------------------------------------------
!  FREQUENCY_TYPE
!
!   cFreqUnits  : unit string for the frequency array (cMHZ, cGHZ, or cLAMBDA)
!   bk          : current wave number k = 2*pi/lambda  [rad/m]
!   lambda      : current free-space wavelength        [m]
!   freq        : current frequency                    [Hz]
!   freq_ghz    : current frequency                    [GHz]  (convenience)
!   freq_mhz    : current frequency                    [MHz]  (convenience)
!   nFreq       : total number of frequencies in the sweep
!   iFreq       : index of the currently active frequency (1-based)
!   array(:)    : frequency sweep values in cFreqUnits
!------------------------------------------------------------------------------
   type FREQUENCY_TYPE
      character(nCharLen)   :: cFreqUnits = cMHZ
      real(wp)              :: bk, lambda, freq, freq_ghz, freq_mhz
      integer               :: nFreq, iFreq
      real(wp)              :: fstep = ZERO   ! step size [cFreqUnits]; 0 = use nFreq
      real(wp), allocatable :: array(:)       ! sweep values in cFreqUnits
   contains
      procedure :: Freq_Set         ! set current frequency by index; updates bk, lambda, freq
      procedure :: Read_Freq_Data   ! read &Frequency_MHz namelist from open file
      procedure :: print_freq       ! print current frequency to output log
      procedure :: deallocate       ! free array(:)
      procedure, private :: init    ! build uniform sweep array (called internally)
   end type FREQUENCY_TYPE

contains

!------------------------------------------------------------------------------
!  init (private): build a uniformly spaced frequency array.
!
!  fmin, fmax  : sweep endpoints in cunits
!  nfreq       : number of points (nfreq=1 gives a single frequency at fmin)
!  cunits      : frequency unit string (cMHZ, cGHZ, or cLAMBDA)
!
!  For nfreq = 1: fdelta = 0, so array(1) = fmin.
!  For nfreq > 1: array(i) = fmin + (i-1) * (fmax-fmin)/(nfreq-1),
!                 giving exact values at both endpoints.
!------------------------------------------------------------------------------
   subroutine init(self, fmax, fmin, nfreq, cunits, fstep_in)
      class(FREQUENCY_TYPE), intent(inout) :: self
      real(wp), intent(in)           :: fmax, fmin
      integer,  intent(in)           :: nfreq
      character(*), intent(in)       :: cunits
      real(wp), intent(in), optional :: fstep_in

      real(wp)  :: fdelta
      integer   :: i, ierr, nf
      logical   :: bUseStep        ! .TRUE. if fstep_in present and > 0
      real(wp), allocatable :: myArray(:)

      if (allocated(self%array)) deallocate(self%array)

      self%cFreqUnits = cunits
      fdelta          = ZERO

      ! ---- check fstep_in separately to avoid present() in compound test ----
      bUseStep = .FALSE.
      if (present(fstep_in)) then
         if (fstep_in > ZERO) bUseStep = .TRUE.
      end if

      if (bUseStep) then
         ! fstep supplied — compute nFreq from step size
         self%fstep = fstep_in
         nf = nint((fmax - fmin) / fstep_in) + 1
         if (nf < 1) nf = 1
         fdelta = fstep_in
      else
         ! nFreq supplied directly
         self%fstep = ZERO
         nf = nfreq
         if (nf > 1) fdelta = (fmax - fmin) / real(nf - 1, wp)
      end if

      self%nfreq = nf

      allocate(myArray(nf), stat=ierr)

      do i = 1, nf
         myArray(i) = fmin + fdelta * real(i - 1, wp)
      end do

      self%array = myArray

   end subroutine init

!------------------------------------------------------------------------------
!  deallocate: free the frequency array.  Safe to call when not allocated.
!------------------------------------------------------------------------------
   subroutine deallocate (this)
      class(FREQUENCY_TYPE), intent(inOUT) :: this
      if (allocated(this%array)) deallocate (this%array)
   end subroutine deallocate

!------------------------------------------------------------------------------
!  Freq_Set: activate frequency index iFreq in the sweep.
!
!  Sets bk, lambda, freq, freq_ghz, freq_mhz from array(iFreq).
!
!  Wave number computation by unit:
!    MHz:    bk = 2*pi * (f_MHz * 1e6) / c  =  2*pi * f_MHz / (c * 1e-6)
!    GHz:    bk = 2*pi * (f_GHz * 1e9) / c  =  2*pi * f_GHz / (c * 1e-9)
!    LAMBDA: the stored value is interpreted as wavelength lambda [m];
!            bk = 2*pi / lambda,  freq = c / lambda
!
!  lambda is always derived as 2*pi / bk (metres) regardless of input unit.
!  Fatal error if iFreq is out of range [1, nFreq].
!------------------------------------------------------------------------------
   subroutine Freq_Set(this, iFreq)
      class(FREQUENCY_TYPE), intent(inOUt) :: this
      integer, intent(in)    :: iFreq

      real(wp) :: Freq, bk0, rconverttoghz

      if (iFreq .lt. 1 .OR. iFreq .gt. this%nFreq) &
         call fatalError('Freqency Set index out of range', 'iFreq', iFreq)

      this%iFreq = iFreq
      Freq = this%array(iFreq)   ! in cFreqUnits

      ! Compute free-space wave number bk = 2*pi*f/c
      select case (this%cFreqUnits)
      case (cMHZ)
         bk0 = TWOPI*Freq/(velOfLight*1.0E-6)   ! Freq [MHz] -> bk [1/m]
         rconverttoghz = 1.0E-3
      case (cGHZ)
         bk0 = TWOPI*Freq/(velOfLight*1.0E-9)   ! Freq [GHz] -> bk [1/m]
         rconverttoghz = 1.0
      case (cLAMBDA)
         bk0 = TWOPI/Freq                        ! Freq treated as lambda [m]
         rconverttoghz = 1.0E9
      case default
         call fatalError('Frequecy Module: Units not recognized', ' ', 0)
      end select

      ! Store bk, lambda, and freq in canonical SI units (Hz)
      this%Bk = bk0
      this%lambda = TWOPI/bk0           ! free-space wavelength [m]

      select case (this%cFreqUnits)
      case (cLAMBDA)
         this%freq = velOfLight/this%lambda  ! derive Hz from wavelength
      case default
         this%freq = Freq                    ! stored value IS the frequency
         ! (unit conversion absorbed into bk)
      end select

      ! Populate convenience fields in GHz and MHz
      select case (this%cFreqUnits)
      case (cMHZ)
         this%freq_ghz = Freq*1.0E-3    ! MHz -> GHz
         this%freq_mhz = Freq
      case (cGHZ)
         this%freq_ghz = Freq
         this%freq_mhz = Freq*1.0E3     ! GHz -> MHz
      case (cLAMBDA)
         this%freq_ghz = this%freq/1.0E9  ! Hz -> GHz
         this%freq_mhz = this%freq/1.0E6  ! Hz -> MHz
      end select

   end subroutine Freq_Set

!------------------------------------------------------------------------------
!  print_freq: print the current frequency to the output log in a bordered box.
!  Prints the stored value in cFreqUnits (not necessarily Hz).
!------------------------------------------------------------------------------
   subroutine print_freq(this)
      class(FREQUENCY_TYPE), intent(in) :: this
      character(80)                     :: cLine

      call out(' ')
      write (cLine, *) '*****************************************************'; call centeredOut(trim(cline))
      write (cLine, *) 'Frequency this Run'; call centeredOut(trim(cLine))
      write (cLine, *) this%freq, ' ', this%cFreqUnits; call centeredOut(trim(cline))
      write (cLine, *) '*****************************************************'; call centeredOut(trim(cline))
      call out(' ')
   end subroutine print_freq

!------------------------------------------------------------------------------
!  Read_Freq_Data: read the &Frequency_MHz namelist group from open file iU.
!
!  Expected namelist format in the .nml input file:
!    &Frequency_MHz
!      fMin  = <real>    ! lower frequency bound [MHz]
!      fMax  = <real>    ! upper frequency bound [MHz]
!      nFreq = <integer> ! number of sweep points
!    /
!
!  After a successful read, calls init() to build the uniform sweep array
!  and sets cFreqUnits = cMHZ.
!
!  Note: only MHz input is currently supported via this namelist path.
!  GHz and LAMBDA sweeps must be constructed via init() directly.
!------------------------------------------------------------------------------
   subroutine Read_Freq_Data(F, iU)
      use vector_and_utility_m   ! for nml_error

      class(FREQUENCY_TYPE), intent(inout) :: F
      integer, intent(in) :: iU

      real(wp)      :: fMin, fMax, fstep
      integer       :: nFreq, ios
      character(80) :: msg

      ! ---- explicit defaults before namelist read ----
      ! (avoids Fortran SAVE behaviour of in-declaration initialisation)
      fMin  = ZERO
      fMax  = ZERO
      fstep = ZERO
      nFreq = -1       ! sentinel: -1 means not supplied in namelist

      namelist /Frequency_MHz/ fmin, fmax, nFreq, fstep

      read (iU, NML=Frequency_MHz, IOSTAT=ios, iomsg=msg)
      write (*, nml=Frequency_MHz)   ! echo namelist to stdout for verification

      call nml_error('Frequency_MHz', ios, msg)  ! fatal if ios /= 0

      ! ---- validate ----
      if (fstep <= ZERO .and. nFreq <= 0) &
         call FatalError('Frequency_MHz: supply fstep > 0 or nFreq > 0', '', 0)

      ! ---- build sweep array ----
      if (fstep > ZERO) then
         ! fstep path — nFreq computed inside init()
         call f%init(fmax, fmin, 1, cMHZ, fstep_in=fstep)
         write (*, '(2x,a,i0,a,f0.4,a)') &
            'Frequency sweep: ', f%nFreq, ' points at ', fstep, ' MHz/step'
      else
         ! nFreq path — existing behaviour unchanged
         call f%init(fmax, fmin, nFreq, cMHZ)
      end if

   end subroutine Read_Freq_Data

end module frequency_m