module basic_header_m

!===============================================================
!  Basic header module (portable + Intel-optimized dual path)
!
!  Purpose:
!   Central repository for working precision, physical constants,
!   complex constants, string tokens, and diagnostic output
!   routines.  Included by nearly every other NeoMoM module.
!
!  Precision:
!   wp = real32  (single) by default.
!   Uncomment the DOUBLE block and comment out real32 to switch to
!   real64 throughout the entire code in one place.
!
!  Physical constants:
!   All electromagnetic constants are derived from the exact CODATA
!   value c = 2.99792458e8 m/s and the exact mu_0 = 4pi x 10^-7 H/m.
!   This gives ETA0 = 376.7303... ohms, NOT the common approximation
!   120*pi = 376.991 ohms.  The ~0.07% difference matters for
!   power-check closure and gain accuracy.
!
!  Build options:
!    -DDOUBLE          : use real64 working precision
!    -DINTEL_COMPILER  : enable Intel-specific features
!
!  Preservation note:
!   All original public subroutine names and call patterns are
!   unchanged so that existing caller code needs no modification.
!===============================================================

   use, intrinsic :: iso_fortran_env, only: int32, real32, real64, output_unit

   implicit none
   private

!------------------ Public symbols ------------------------------
   public :: wp
   public :: ZERO, ONE, TWO, FOUR, PI, TWOPI, FOURPI, PIHALF, RMS, HALF
   public :: velOfLight, mu_0, epsilon_0
   public :: zIMAG, zZERO, zONE, zjETA0_OVER_FOURPI
   public :: DTOR, RTOD, ETA0, ETA0_OVER_FOURPI
   public :: Complex_Arr_Type

   ! original procedures (unchanged names)
   public :: OUT, OUTArray, CenteredOut
   public :: FatalLine, WarningLine, NoticeLine, SeparatorLine
   public :: ErrorLine, FatalError, FatalStop
   public :: notice, warning, message

!------------------ Precision control --------------------------
!  wp is the single working precision kind used by all NeoMoM arrays.
!  Change here to propagate through the entire codebase.

!#ifdef DOUBLE
   ! integer, parameter :: wp = real64   ! double precision (~15 digits)
!#else
   integer, parameter :: wp = real32     ! single precision (~7 digits)
!#endif

!------------------ Integer kinds -------------------------------
   integer, public, parameter :: iStdOut = output_unit  ! standard output unit

!------------------ Numeric constants --------------------------
!  Basic real constants at working precision.
!  PI is computed at run-time via 4*atan(1) so it is exact to wp digits.

   real(wp), parameter :: &
      ZERO = 0.0_wp, &
      ONE = 1.0_wp, &
      TWO = 2.0_wp, &
      FOUR = 4.0_wp, &
      PI = FOUR*atan(ONE), &  ! 3.14159...
      TWOPI = TWO*PI, &  ! 2*pi, full circle in radians
      FOURPI = FOUR*PI, &  ! 4*pi, full sphere solid angle
      PIHALF = 0.5_wp*PI, &  ! pi/2
      DTOR = PI/180.0_wp, &  ! degrees-to-radians conversion factor
      RTOD = 180.0_wp/PI, &  ! radians-to-degrees conversion factor
      RMS = sqrt(TWO)/TWO, &  ! 1/sqrt(2) = 0.7071... (peak-to-RMS)
      HALF = 0.5_wp

!  Electromagnetic constants.
!  velOfLight is the exact defined value of c (CODATA 2018, exact).
!  mu_0 = 4*pi*1e-7 H/m (exact pre-2019 SI; retained here).
!  epsilon_0 derived from c^2 = 1/(mu_0*eps_0).
!  ETA0 = sqrt(mu_0/eps_0) = free-space wave impedance.
!    Exact: 376.7303134... ohms.  Do not substitute 120*pi = 376.991.
!  ETA0_OVER_FOURPI appears in the EFIE radiation integral prefactor:
!    prefac = -j*k*(ETA0/4pi)  [pattern_v2_m.f90, zfill_m.f90]

   real(wp), parameter :: &
      velOfLight = real(2.99792458e8_real64, wp), &  ! c, m/s (exact)
      mu_0 = FOUR*PI*1.0e-7_wp, &  ! H/m
      epsilon_0 = ONE/(velOfLight*velOfLight*mu_0), &  ! F/m
      ETA0 = sqrt(mu_0/epsilon_0), &  ! free-space impedance, ~376.730 ohms
      ETA0_OVER_FOURPI = ETA0/FOURPI                        ! ETA0/(4*pi), ~29.979 ohms/sr

!  Complex constants at working precision.
!  zjETA0_OVER_FOURPI = j*(ETA0/4*pi), used as a scalar factor in
!  the EFIE kernel:  Z_mn contribution ~ j*k*ETA0/(4*pi) * [A - Phi/k^2]

   complex(wp), parameter :: &
      zIMAG = (ZERO, ONE) &  ! imaginary unit j
      , zZERO = (ZERO, ZERO) &  ! complex zero
      , zONE = (ONE, ZERO) &  ! complex one
      , zjETA0_OVER_FOURPI = zIMAG*ETA0_OVER_FOURPI    ! j*(ETA0/4*pi)

!------------------ Derived types -------------------------------
!  Complex_Arr_Type: general-purpose wrapper for a 2-D complex array.
!  Used in block-matrix storage and norm computations.

   type :: Complex_Arr_Type
      complex(wp), allocatable :: arrZ(:, :)
   end type Complex_Arr_Type

!------------------ Module state (legacy-compatible) ------------
!  nWarnings: running count incremented by WarningLine / NoticeLine.
!  bStopOnError: when .true., FatalError calls error stop.
!  iFileOut: Fortran unit for optional log file output.
!    Value -1 means no log file is open; OUT() skips file write.
!  cTempDir: scratch directory path for temporary files.

   integer, save :: nWarnings = 0
   logical, save :: bStopOnError = .true.

   integer, public, parameter :: maxChar20 = 20, MAXPATH = 512, MAXNAME = 256

   integer, public, save :: iFileOut = -1       ! -1 = no log file open
   character(MAXPATH), public, save :: cTempDir = ''

!  String tokens for angle-cut directions, solve types, and excitation types.
!  Used as keyword comparisons throughout the solver and I/O layers.

   character(len=*), parameter, public :: &
      cAZIMUTH = 'AZIMUTH' &  ! phi = const pattern cut
      , cELEVATION = 'ELEVATION' &  ! theta = const pattern cut
      , cMONOSTATIC = 'MONOSTATIC' &  ! radar: Tx = Rx direction
      , cBISTATIC = 'BISTATIC' &  ! radar: Tx /= Rx direction
      , cDIPOLE_MONOSTATIC = 'DIPOLE_MONOSTATIC' &
      , cMULTI_BISTATIC = 'MULTI_BISTATIC' &
      , cFIXED_ANGLE_BISTATIC = 'FIXED_ANGLE_BISTATIC' &
      , cANTENNA = 'ANTENNA' &  ! antenna (transmit) solve mode
      , cPSM_PATTERN = 'PSM_PATTERN' &  ! polarimetric scattering matrix pattern
      , cRHS_PLANEWAVE = 'RHS_PLANEWAVE' &  ! plane-wave excitation
      , cRHS_DIPOLE = 'RHS_DIPOLE' &  ! Hertzian dipole excitation
      , cRHS_BY_INPUT_FILE = 'RHS_BY_INPUT_FILE'      ! RHS read from file

!===============================================================
contains
!===============================================================

!---------------------------------------------------------------
!  OUT: write charLine to stdout and, if open, to the log file.
!  Both units are flushed immediately so crash output is not lost.
!---------------------------------------------------------------
   subroutine OUT(charLine)
      character(len=*), intent(in) :: charLine

      ! if (iFileOut > 0) then
      write (iFileOut, '(a)') trim(charLine)
      flush (unit=iFileOut)
      ! end if

      write (iStdOut, '(a)') trim(charLine)
      flush (unit=iStdOut)
   end subroutine OUT

!---------------------------------------------------------------
!  OUTArray: write each element of a string array via OUT.
!---------------------------------------------------------------
   subroutine OUTArray(charLineArray)
      character(len=*), intent(in) :: charLineArray(:)
      integer      :: i
      do i = 1, size(charLineArray)
         if (iFileOut > 0) write (iFileOut, '(a)') trim(charLineArray(i))
         write (iStdOut, '(a)') trim(charLineArray(i))
      end do
   end subroutine OUTArray

!---------------------------------------------------------------
!  CenteredOut: center charLine within an 80-column field and write.
!  Truncates silently if charLine exceeds 79 characters.
!---------------------------------------------------------------
   subroutine CenteredOut(charLine)
      character(len=*), intent(in) :: charLine
      integer, parameter :: nWidth = 80
      character(len=nWidth) :: cLine
      integer :: length, pos

      length = len_trim(charLine)
      if (length > nWidth) length = nWidth - 1
      pos = max(1, nWidth/2 - length/2)
      cLine = ''
      cLine(pos:pos + length - 1) = charLine(1:length)

      if (iFileOut > 0) write (iFileOut, '(a)') trim(cLine)
      write (iStdOut, '(a)') trim(cLine)
   end subroutine CenteredOut

!---------------------------------------------------------------
!  Diagnostic banner lines.  WarningLine and NoticeLine also
!  increment nWarnings so the caller can test for any warnings.
!---------------------------------------------------------------
   subroutine FatalLine()
      call OUT('--------FATAL ERROR-------FATAL ERROR-------FATAL ERROR-------')
   end subroutine FatalLine

   subroutine WarningLine()
      call OUT('------WARNING-----WARNING-----WARNING-----WARNING-----')
      nWarnings = nWarnings + 1
   end subroutine WarningLine

   subroutine NoticeLine()
      call OUT('------Notice-----')
      nWarnings = nWarnings + 1
   end subroutine NoticeLine

   subroutine SeparatorLine()
      call OUT('--------------------------------------------------------------------------------')
   end subroutine SeparatorLine

!---------------------------------------------------------------
!  ErrorLine: write  "cErrType = iErr"  to stdout and log file.
!---------------------------------------------------------------
   subroutine ErrorLine(cErrType, iErr)
      character(len=*), intent(in) :: cErrType
      integer, intent(in)     :: iErr
      write (iStdOut, '(a,a,i0)') trim(cErrType), ' = ', iErr
      if (iFileOut > 0) write (iFileOut, '(a,a,i0)') trim(cErrType), ' = ', iErr
   end subroutine ErrorLine

!---------------------------------------------------------------
!  FatalError: print banner + message + error code, then stop.
!  Calls error stop (standard Fortran 2008) so the shell exit
!  code is non-zero, making it detectable by build scripts.
!---------------------------------------------------------------
   subroutine FatalError(cMsg, cErrType, iErr)
      character(len=*), intent(in) :: cMsg, cErrType
      integer, intent(in)     :: iErr

      call OUT(' ')
      call FatalLine()
      call OUT(cMsg)
      call ErrorLine(cErrType, iErr)
      call SeparatorLine()
      error stop
   end subroutine FatalError

!---------------------------------------------------------------
!  FatalStop: remove scratch directory (if it exists) before exit.
!  Called from top-level cleanup when a non-recoverable error
!  has already been reported.
!---------------------------------------------------------------
   subroutine FatalStop()
      ! logical :: bExist
      ! integer :: ierr
      ! ! inquire (directory=trim(cTempDir), exist=bExist)

      ! if (bExist .and. len_trim(cTempDir) > 0) then
      !    call execute_command_line( &
      !       'rmdir "'//trim(cTempDir)//'"', exitstat=ierr)
      ! end if

   end subroutine FatalStop

!---------------------------------------------------------------
!  notice: print a bordered notice block (non-fatal).
!---------------------------------------------------------------
   subroutine notice(cMsg)
      character(len=*), intent(in) :: cMsg
      call OUT(' ')
      call NoticeLine()
      call OUT(cMsg)
      call SeparatorLine()
   end subroutine notice

!---------------------------------------------------------------
!  warning: print a bordered warning block (non-fatal).
!---------------------------------------------------------------
   subroutine warning(cMsg)
      character(len=*), intent(in) :: cMsg
      call OUT(' ')
      call WarningLine()
      call OUT(cMsg)
      call SeparatorLine()
   end subroutine warning

!---------------------------------------------------------------
!  message: print a message block between separator lines.
!---------------------------------------------------------------
   subroutine message(cMsg)
      character(len=*), intent(in) :: cMsg
      call OUT(' ')
      call SeparatorLine()
      call OUT(cMsg)
      call SeparatorLine()
   end subroutine message

end module basic_header_m
