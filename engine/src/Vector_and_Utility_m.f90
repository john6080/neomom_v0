Module vector_and_utility_m

!===============================================================
!  Vector and utility module
!
!  Purpose:
!   Provides operator-overloaded vector algebra, norm computations,
!   dB conversions, complex-to-polar conversion, file/string parsing
!   utilities, and miscellaneous helpers used throughout NeoMoM.
!
!  Key operators defined here:
!   .CROSS.     -- cross product, all real/complex combinations
!   .NORM.      -- L2 (Euclidean) norm, real/complex vector and matrix
!   .DiagNORM.  -- Frobenius norm of upper-triangular matrix
!   .LoneNORM.  -- L1 (Manhattan) norm of a 3-vector
!   .TIMEAVE.   -- time-averaged (RMS) magnitude of a complex field
!
!  Dependencies: basic_header_m (wp, ZERO, HALF, RTOD, RMS,
!                fatalError, CenteredOut, SeparatorLine, Complex_Arr_Type)
!===============================================================

   use basic_header_m
   implicit none
   private

   public ::  OPERATOR(.CROSS.) &
             , dBv, dBp, zP, zPdBV &
             , Get_File_extension &
             , Create_Unique_List_of_Integers &
             , Index_of_integer_in_List &
             , Position_File_To_KeyWord &
             , VA_Attention_Box, VA_Attention_Box_2 &
             , position_file_to_key_word_v2 &
             , Position_File_To_KeyWord_hash &
             , Text_to_right &
             , Copy_File &
             , Integer_to_right_of_Equal &
             , Text_to_right_of_Equal &
             , Real_to_Right_of_Equal &
             , Complex_to_Right_of_Equal &
             , real_value_after_equal &
             , char_value_after_equal &
             , toUpper &
             , write_complex_rect &
             , nml_error

!---------------------------------------------------------------
!  .NORM. operator -- L2 norm for real/complex vectors and matrices.
!  Overloaded for:
!   real_vector_norm       : sqrt(sum(v_i^2))
!   cmplx_vector_norm      : sqrt(sum|z_i|^2)  [dot_product conjugates 1st arg]
!   cmplx_matrix_norm      : Frobenius norm, sqrt(sum over all elements |z_ij|^2)
!   cmplx_UV_norm          : norm of matrix product U*V
!   cmplx_Block_Array_norm : norm across an array of Complex_Arr_Type blocks
!---------------------------------------------------------------
   interface OPERATOR(.NORM.)
      MODULE PROCEDURE real_vector_norm     &
         , cmplx_vector_norm               &
         , cmplx_matrix_norm               &
         , cmplx_UV_norm                   &
         , cmplx_Block_Array_norm
   end interface

!  .DiagNORM.: Frobenius norm treating input as upper-triangular;
!  the lower triangle is recovered by symmetry (factor of 2 on off-diagonal).
   interface OPERATOR(.DiagNORM.)
      MODULE PROCEDURE cmplx_diag_matrix_norm
   end interface

!  .LoneNORM.: L1 (sum of absolute values) for a 3-vector.
   interface OPERATOR(.LoneNORM.)
      MODULE PROCEDURE real_vector_L1_norm
   end interface

!---------------------------------------------------------------
!  .CROSS. operator -- cross product A x B for 3-vectors.
!  All four real/complex combinations are handled:
!   real   x real,   complex x complex,
!   real   x complex, complex x real
!---------------------------------------------------------------
   interface OPERATOR(.CROSS.)
      MODULE PROCEDURE real_vector_cross_product
      MODULE PROCEDURE real_complex_vector_cross_product
      MODULE PROCEDURE complex_real_vector_cross_product
      MODULE PROCEDURE complex_vector_cross_product
   end interface

!  .TIMEAVE.: time-averaged (RMS) magnitude of a complex phasor field
!  vector, = (1/sqrt(2)) * |z|.  Used for time-averaged power density.
   interface operator(.TIMEAVE.)
      module procedure complex_time_average
   end interface

CONTAINS

!===============================================================
!  Namelist error handler
!===============================================================

!---------------------------------------------------------------
!  nml_error: call fatalError if ios /= 0 after a namelist read.
!  cWhere: calling location string for diagnostic context.
!  cMsg:   namelist group or variable name being read.
!---------------------------------------------------------------
   subroutine nml_error(cWhere, ios, cMsg)
      character(*), intent(in) :: cWhere, cMsg
      integer, intent(in) :: ios
      if (ios /= 0) &
         call fatalError(trim(cWhere)//' namelist read error: '//trim(cMsg), 'iostat', ios)
   end subroutine nml_error

!===============================================================
!  Diagnostic output utilities
!===============================================================

!---------------------------------------------------------------
!  write_complex_rect: write a complex number in rectangular form
!  "(Re, Im)" to the given Fortran unit, with optional label.
!  Format: ES13.6 for both parts (scientific notation, 6 sig figs).
!---------------------------------------------------------------
   subroutine write_complex_rect(unit, z, label)
      integer, intent(in)           :: unit
      complex, intent(in)           :: z
      character(len=*), intent(in), optional :: label

      if (present(label)) then
         write (unit, '(a,1x,"(",es13.6,",",1x,es13.6,")")') &
            trim(label), real(z), aimag(z)
      else
         write (unit, '("(",es13.6,",",1x,es13.6,")")') &
            real(z), aimag(z)
      end if
   end subroutine write_complex_rect

!===============================================================
!  String utilities
!===============================================================

!---------------------------------------------------------------
!  toUpper: convert string to upper case in place.
!  Thin public wrapper around the private change_to_upper_case.
!---------------------------------------------------------------
   subroutine toUpper(string)
      CHARACTER(LEN=*), INTENT(INOUT) :: string
      call change_to_upper_case(string)
   end subroutine toUpper

!---------------------------------------------------------------
!  change_to_upper_case: private pure worker, converts ASCII
!  lower-case letters (97-122) to upper case (65-90) in place.
!---------------------------------------------------------------
   pure SUBROUTINE change_to_upper_case(string)
      CHARACTER(LEN=*), INTENT(INOUT) :: string
      INTEGER             :: i
      CHARACTER(LEN=1)    :: char
      DO i = 1, LEN(string)
         char = string(i:i)
         IF (IACHAR(char) >= 97 .AND. IACHAR(char) <= 122) char = ACHAR(IACHAR(char) - 32)
         string(i:i) = char
      END DO
   END SUBROUTINE change_to_upper_case

!===============================================================
!  File I/O utilities
!===============================================================

!---------------------------------------------------------------
!  real_value_after_equal: scan file iU for cKeyWord, then read
!  the real value on the right-hand side of the "=" on that line.
!  Fatal error if the keyword is not found.
!---------------------------------------------------------------
   real function real_value_after_equal(cKeyWord, iU)
      integer, intent(in) :: iU
      character(*), intent(in) :: cKeyWord

      character(80) :: cLine, cTextOut
      logical       :: bErr

      bErr = Position_File_To_KeyWord(iU, trim(adjustl(cKeyWord)))
      if (.NOT. bErr) call fatalError('read_value_after_equal', '', 0)

      backspace (iU); read (iU, '(A)') cLine
      call Text_to_right('=', cTextOut, trim(adjustl(cLine)), bErr)
      if (bErr) call fatalError('Text_to_right', '', 0)

      read (cTextOut, *) real_value_after_equal
   end function real_value_after_equal

!---------------------------------------------------------------
!  char_value_after_equal: scan file iU for cKeyWord, return the
!  character text to the right of "=" on that line.
!  If optional bErr is present, it is set .true. on failure and
!  the routine returns without stopping.  Otherwise fatal error.
!---------------------------------------------------------------
   function char_value_after_equal(cKeyWord, iU, bErr) result(char_value)
      integer, intent(in) :: iU
      character(*), intent(in) :: cKeyWord
      logical, optional   :: bErr

      character(1024) :: cLine, cTextOut
      logical         :: bFail
      character(1024) :: char_value

      if (.NOT. Position_File_To_KeyWord(iU, trim(adjustl(cKeyWord)))) then
         if (present(bErr)) then
            bErr = .true.; return
         end if
         call fatalError('Position_File_To_KeyWord', trim(adjustl(cKeyWord)), 0)
      end if

      backspace (iU); read (iU, '(A)') cLine
      call Text_to_right('=', cTextOut, trim(adjustl(cLine)), bFail)

      if (present(bErr)) then
         bErr = bFail
         if (bErr) return
      end if

      if (bFail) call fatalError('Text_to_right', trim(adjustl(cKeyWord)), 0)

      char_value = trim(adjustl(cTextOut))
   end function char_value_after_equal

!---------------------------------------------------------------
!  Complex_to_Right_of_Equal: parse "... = Re Im" from cLineIn.
!  Returns .true. (bFailed) if "=" is absent or parse fails.
!  zOut is set to cmplx(Re, Im) on success.
!---------------------------------------------------------------
   logical function Complex_to_Right_of_Equal(cLineIn, zOut)
      character(*), intent(in)  :: cLineIn
      complex, intent(out) :: zOut

      integer :: iPos, ios
      logical :: bFailed
      character(1), parameter :: char = '='
      character(20) :: cText
      real          :: zr, zi

      bFailed = .TRUE.
      iPos = index(cLineIn, char)

      if (iPos == 0) bFailed = .false.

      cText = trim(adjustL(cLineIn(iPos + 1:)))
      read (cText, *, iostat=ios) zr, zi

      if (ios /= 0) bFailed = .TRUE.
      zOut = cmplx(zr, zi)
      Complex_to_Right_of_Equal = bFailed
   end function Complex_to_Right_of_Equal

!---------------------------------------------------------------
!  Real_to_Right_of_Equal: parse "... = value" from cLineIn.
!  Returns .true. (bFailed) if "=" absent or parse fails.
!---------------------------------------------------------------
   logical function Real_to_Right_of_Equal(cLineIn, rOut)
      character(*), intent(in)  :: cLineIn
      real, intent(out) :: rOut

      integer :: iPos, ios
      logical :: bFailed
      character(1), parameter :: char = '='
      character(20) :: cText

      bFailed = .TRUE.
      iPos = index(cLineIn, char)

      if (iPos == 0) bFailed = .false.

      cText = trim(adjustL(cLineIn(iPos + 1:)))
      read (cText, *, iostat=ios) rOut

      if (ios /= 0) bFailed = .TRUE.
      Real_to_Right_of_Equal = bFailed
   end function Real_to_Right_of_Equal

!---------------------------------------------------------------
!  Text_to_Right_of_Equal: return the trimmed text to the right
!  of "=" in cLineIn.  Returns .false. (success) / .true. (not found).
!---------------------------------------------------------------
   logical function Text_to_Right_of_Equal(cLineIn, cOUt)
      character(*), intent(in)  :: cLineIn
      character(30), intent(out) :: cOUt

      integer :: iPos
      logical :: bFailed
      character(1), parameter :: char = '='

      bFailed = .FALSE.
      iPos = index(cLineIn, char)

      if (iPos == 0) bFailed = .TRUE.
      cOUt = trim(adjustL(cLineIn(iPos + 1:)))
      Text_to_Right_of_Equal = bFailed
   end function Text_to_Right_of_Equal

!---------------------------------------------------------------
!  Integer_to_right_of_Equal: parse "... = integer" from cLineIn.
!  Returns .true. (bFailed) on "=" absent or parse failure.
!---------------------------------------------------------------
   logical function Integer_to_right_of_Equal(cLineIn, iNumOUt)
      character(*), intent(in)  :: cLineIn
      integer, intent(out) :: iNumOUt

      integer :: iPos, ios
      logical :: bFailed
      character(20) :: cText
      character(1), parameter  :: char = '='

      bFailed = .FALSE.
      iPos = index(cLineIn, char)

      if (iPos == 0) bFailed = .true.

      cText = trim(adjustL(cLineIn(iPos + 1:)))
      read (cText, *, iostat=ios) iNumOUt
      if (ios /= 0) bFailed = .TRUE.
      Integer_to_right_of_Equal = bFailed
   end function Integer_to_right_of_Equal

!---------------------------------------------------------------
!  Copy_File: rewind iUin and copy all lines to iUout,
!  wrapped in header/footer banners.  Both units must be open.
!  Used to echo the input file into the output log.
!---------------------------------------------------------------
   subroutine Copy_File(iUin, iUout)
      integer, intent(in) :: iUin, iUout
      character(256) :: cLine

      rewind (iUin)

      write (iUout, *)
      write (iUout, '(a,a,a)') '                   ---|  Input File |---'
      write (iUout, *)

      do
         read (iUin, '(A)', end=10) cLine
         write (iUout, '(A)') trim(cLine)
      end do

10    continue
      write (iUout, *)
      write (iUout, '(a)') '                      ---| End Of Copied Input Data |---'
      call separatorline()
      write (iUout, *)
   end subroutine Copy_File

!---------------------------------------------------------------
!  Text_to_right: return the trimmed text to the right of the
!  first occurrence of char in cLineIn.
!  bErrNotFound = .true. if char is not present.
!  If char is not found iPos = 0, so cTextOut = trim(cLineIn(1:))
!  i.e., the whole string.  Caller must check bErrNotFound.
!---------------------------------------------------------------
   subroutine Text_to_right(char, cTextOut, cLineIn, bErrNotFound)
      character(1), intent(in)  :: char
      character(*), intent(in)  :: cLineIn
      character(*), intent(out) :: cTextOut
      logical, intent(out) :: bErrNotFound

      integer :: iPos

      bErrNotFound = .FALSE.
      iPos = index(cLineIn, char)

      if (iPos == 0) then
         bErrNotFound = .TRUE.
      end if

      cTextOut = trim(adjustL(cLineIn(iPos + 1:)))
   end subroutine Text_to_right

!---------------------------------------------------------------
!  Position_File_To_KeyWord_hash: rewind iU and scan for cKeyWord
!  in lines that begin with '#'.  Case-insensitive comparison.
!  Returns .true. if found, .false. otherwise.
!  Used for hash-prefixed configuration files.
!---------------------------------------------------------------
   logical function Position_File_To_KeyWord_hash(iU, cKeyWord)
      integer, intent(in) :: iU
      character(*), intent(in) :: cKeyWord
      character(80) :: cLine, cKey
      integer       :: iErr, n
      character(*), parameter :: cSub = 'Subroutine Position_File_To_KeyWord_hash( File, cKeyWord )'

      Position_File_To_KeyWord_hash = .FALSE.
      cKey = adjustl(trim(cKeyWord))
      call change_to_UPPER_case(cKey)
      n = len(adjustl(trim(cKey)))
      rewind (iU)

      do
         read (iU, '(A)', iostat=iErr) cLine
         if (iErr /= 0) exit

         cLine = adjustL(trim(cLine))
         call change_to_UPPER_case(cLine)

         if (index(cLine, cKey(1:n)) /= 0) then
            Position_File_To_KeyWord_hash = .TRUE.
            exit
         end if
      end do
   end function Position_File_To_KeyWord_hash

!---------------------------------------------------------------
!  position_file_to_key_word_v2: extended keyword search.
!  Searches from current position (bRewind=.false.) or from the
!  start (bRewind=.true.) for the nOccurrances-th occurrence of
!  cKeyWordIn as the leading characters of a line (case-sensitive).
!  iLineNumber is updated as lines are read.
!  bUnformatted_in=.true. reads a binary-format file.
!  Returns .false. if the keyword is found, .true. otherwise
!  (note: inverted convention from the hash variant).
!---------------------------------------------------------------
   logical function position_file_to_key_word_v2(iU, cKeyWordIn, bRewind, nOccurrances, iLineNumber, bUnformatted_in)
      integer, intent(in)    :: iU, nOccurrances
      character(*), intent(in)    :: cKeyWordIn
      logical, intent(in)    :: bRewind
      integer, intent(inOut) :: iLineNumber
      logical, optional, intent(in) :: bUnformatted_in

      character :: cKeyWord*20, cLine*79
      integer       :: k, iErr, nfound
      logical       :: bUnformatted = .FALSE.

      character(*), parameter :: cSub = ' subroutine position_file_to_key_word( iU, cKeyWordIn, iLineNumberInOut, bErr ) :'

      if (present(bUnformatted_in)) bUnformatted = bUnformatted_in
      position_file_to_key_word_v2 = .TRUE.
      cKeyWord = adjustL(cKeyWordIn)

      nfound = 0
      iLineNumber = 0
      k = len(trim(cKeyWord))

      if (bRewind) rewind (iU)

      do
         if (bUnformatted) then
            read (iU, iostat=iErr, end=9000) cLine(1:k)
         else
            read (iU, '(A)', iostat=iErr, end=9000) cLine
         end if

         if (iErr == 67) cycle  ! record shorter than requested read length, skip

         if (iErr /= 0) call fatalError(cSub//'Failure to find key word '//cKeyWord, 'iErr', iErr)

         cLine = adjustL(trim(cLine))
         iLineNumber = iLineNumber + 1

         if (cLine(1:k) == cKeyWord(1:k)) then
            nfound = nfound + 1
            if (nfound == nOccurrances) exit
         end if
      end do

      position_file_to_key_word_v2 = .false.
      return

9000  continue  ! end-of-file reached before keyword found
   end function

!---------------------------------------------------------------
!  Position_File_To_KeyWord: rewind iU and scan for cKeyWord as
!  the leading characters of any line (case-insensitive).
!  Special case: if cKeyWord begins with '&' (namelist group),
!  the file is backspaced after the match so the caller can
!  re-read the matched line for namelist processing.
!  Returns .true. if found, .false. otherwise.
!---------------------------------------------------------------
   logical function Position_File_To_KeyWord(iU, cKeyWord)
      integer, intent(in) :: iU
      character(*), intent(in) :: cKeyWord
      character(80) :: cLine, cKey
      integer       :: iErr, n
      character(*), parameter :: cSub = 'Subroutine Position_File_To_KeyWord( File, cKeyWord )'
      logical       :: bRet

      Position_File_To_KeyWord = .FALSE.
      cKey = adjustl(trim(cKeyWord))
      call change_to_UPPER_case(cKey)
      n = len(adjustl(trim(cKey)))
      rewind (iU)

      inquire (unit=iU, OPENED=bRet)

      iErr = 0
      do
         read (iU, '(A)', iostat=iErr) cLine
         if (iErr /= 0) exit

         cLine = adjustL(trim(cLine))
         call change_to_UPPER_case(cLine)

         if (cLine(1:n) == cKey(1:n)) then
            if (cKey(1:1) == '&') backspace (iU)  ! leave file positioned for namelist read
            Position_File_To_KeyWord = .TRUE.
            exit
         end if
      end do
   end function Position_File_To_KeyWord

!===============================================================
!  Formatted attention boxes for prominent output messages
!===============================================================

!---------------------------------------------------------------
!  VA_Attention_Box_2: print nLines of centered text in a
!  bordered box.  cLines(:) provides the text lines.
!---------------------------------------------------------------
   Subroutine VA_Attention_Box_2(cLines, nLines)
      character(*), intent(in) :: cLines(:)
      integer, intent(in) :: nLines
      integer      :: iLine

      call CenteredOut(' ')
      call CenteredOut('********************************')
      call CenteredOut(' ')
      do iLine = 1, nLines
         call CenteredOut(cLines(iLine))
         call CenteredOut(' ')
      end do
      call CenteredOut('********************************')
      call CenteredOut(' ')
   end subroutine VA_Attention_Box_2

!---------------------------------------------------------------
!  VA_Attention_Box: print a centered box with a text label and
!  a real number (ES10.2 format) on separate lines.
!---------------------------------------------------------------
   Subroutine VA_Attention_Box(cTxt, rNum)
      character(*), intent(in) :: cTxt
      real(wp), intent(in) :: rNum

      integer      :: l
      character(80) :: cLine1, cLine2

      l = len(trim(cTxt))
      write (cLine1, '(A)') trim(cTxt)
      write (cLine2, '(ES10.2)') rNum

      call CenteredOut(' ')
      call CenteredOut('********************************')
      call CenteredOut(' ')
      call CenteredOut(cLine1)
      call CenteredOut(' ')
      call CenteredOut(cLine2)
      call CenteredOut(' ')
      call CenteredOut('********************************')
      call CenteredOut(' ')
   end subroutine VA_Attention_Box

!===============================================================
!  Integer list utilities
!===============================================================

!---------------------------------------------------------------
!  Create_Unique_List_of_Integers: given InList of positive
!  integers, return iOutList containing each value exactly once,
!  preserving first-occurrence order.
!  Assumes all values in InList are positive (sentinel = -huge).
!  O(n^2) -- adequate for the small lists (wire/segment counts)
!  encountered in NeoMoM geometry processing.
!---------------------------------------------------------------
   pure subroutine Create_Unique_List_of_Integers(iOutList, InList)
      integer, allocatable, intent(out) :: iOutList(:)
      integer, intent(in)  :: inList(:)

      integer, allocatable :: iTempList(:)
      integer      :: nList, nItems_in_List, k, i, iV, iTest_Value
      logical      :: bInList

      nList = size(inList)
      allocate (iTempList(nList))
      iTempList(:) = -huge(1)   ! negative sentinel marks unused slots
      nItems_in_List = 0

      do k = 1, nList
         iV = inList(k)
         bInList = .FALSE.

         do i = 1, nList
            iTest_Value = iTempList(i)
            if (iTest_Value == iV) then
               binList = .TRUE.
               exit
            end if
         end do

         if (.NOT. binList) then
            do i = 1, nList
               iTest_Value = iTempList(i)
               if (iTest_Value < 0) then
                  nItems_in_List = nItems_in_List + 1
                  iTempList(i) = iV
                  exit
               end if
            end do
         end if
      end do

      allocate (iOutList(nItems_in_List))
      iOutList(:) = iTempList(1:nItems_in_List)
   end subroutine Create_Unique_List_of_Integers

!---------------------------------------------------------------
!  Index_of_integer_in_List: return the 1-based position of iIn
!  in iList, or -huge(1) if not found.
!  Fatal error if the loop exhausts iList (iIn truly absent).
!---------------------------------------------------------------
   integer function Index_of_integer_in_List(iIn, iList)
      integer, intent(in) :: iIn, iList(:)
      integer      :: k, nSize

      Index_of_integer_in_List = -huge(1)
      nSize = size(iList)

      do k = 1, nSize
         if (iIn == iList(k)) then
            Index_of_integer_in_List = k
            exit
         end if
      end do

      if (k > nSize) call fatalError(' function Is_Integer_in_List( iIn, iList ): k not in List', 'k=', k)
   end function Index_of_integer_in_List

!===============================================================
!  File extension utility
!===============================================================

!---------------------------------------------------------------
!  Get_File_extension: return the extension of cFileIn (text
!  after the last '.'), converted to upper case.
!  Returns empty string if no '.' is found.
!---------------------------------------------------------------
   function Get_File_extension(cFileIn) result(cExt)
      character(len=*), intent(in)    :: cFileIn
      character(len=20)    :: cExt
      integer      :: iDum, iLen

      iDum = scan(cFileIn, '.', back=.true.)  ! position of last '.'
      iLen = len(trim(cFileIn))
      cExt = cFileIn(iDum + 1:iLen)
      call change_to_upper_case(cExt)
      cExt = trim(cExt)
   end function Get_File_extension

!===============================================================
!  Norm functions
!===============================================================

!---------------------------------------------------------------
!  cmplx_UV_norm: Frobenius norm of the matrix product U*V.
!  Computed via matmul then .NORM., avoiding explicit storage
!  of a temporary matrix.
!---------------------------------------------------------------
   pure Function cmplx_UV_norm(U, V) result(aNorm)
      complex(wp), intent(in) :: U(:, :), V(:, :)
      real(wp)                           :: aNorm
      aNorm = .NORM. (matMul(U, V))
   end function cmplx_UV_norm

!---------------------------------------------------------------
!  cmplx_diag_matrix_norm: Frobenius norm of a full matrix stored
!  as upper triangle only.  Off-diagonal elements are doubled
!  (Hermitian symmetry assumed) before accumulation.
!---------------------------------------------------------------
   pure Function cmplx_diag_matrix_norm(DiagMatrix) result(aNorm)
      complex(wp), intent(in) :: DiagMatrix(:, :)
      real(wp)                 :: aNorm
      integer      :: j, k

      aNorm = ZERO
      do j = 1, size(DiagMatrix, 2)
         k = j - 1                                             ! number of off-diagonal entries in col j
         aNorm = aNorm + TWO*(.NORM.DiagMatrix(1:k, j))**2    ! double off-diagonal contribution
         aNorm = aNorm + DiagMatrix(j, j)*conjg(DiagMatrix(j, j))  ! diagonal (real, positive)
      end do
      aNorm = sqrt(aNorm)
   end function cmplx_diag_matrix_norm

!---------------------------------------------------------------
!  cmplx_Block_Array_norm: Frobenius norm across an array of
!  Complex_Arr_Type blocks (sum of squared element norms).
!---------------------------------------------------------------
   pure Function cmplx_Block_Array_norm(BlkArr) result(aNorm)
      type(Complex_Arr_Type), intent(in) :: BlkArr(:)
      real(wp)                              :: aNorm
      integer      :: iBlk

      aNorm = ZERO
      do iBlk = 1, size(BlkArr)
         aNorm = aNorm + (.NORM.BlkArr(iBlk)%arrZ(:, :))**2
      end do
      aNorm = sqrt(aNorm)
   end function cmplx_Block_Array_norm

!---------------------------------------------------------------
!  real_vector_L1_norm: L1 (Manhattan) norm = sum(|v_i|).
!  Used as a fast non-negative scalar measure of vector magnitude.
!---------------------------------------------------------------
   pure FUNCTION real_vector_L1_norm(Vec) RESULT(L1_norm)
      real(wp), intent(in) :: Vec(3)
      real(wp)             :: L1_norm
      L1_norm = sum(abs(Vec))
   END FUNCTION real_vector_L1_norm

!---------------------------------------------------------------
!  real_vector_norm: L2 (Euclidean) norm via dot_product.
!---------------------------------------------------------------
   pure FUNCTION real_vector_norm(Vec) RESULT(norm)
      real(wp), intent(in) :: Vec(:)
      real(wp)             :: norm
      norm = sqrt(dot_product(Vec, Vec))
   END FUNCTION real_vector_norm

!---------------------------------------------------------------
!  cmplx_matrix_norm: Frobenius norm of a complex matrix.
!  Computed column by column: norm = sqrt(sum_j sum_i |z_ij|^2).
!  Note: Fortran's dot_product conjugates the first argument for
!  complex arrays, giving sum(conjg(z_i)*z_i) = sum(|z_i|^2). OK.
!---------------------------------------------------------------
   pure FUNCTION cmplx_matrix_norm(zMat) RESULT(norm)
      complex(wp), intent(in) :: zMat(:, :)
      real(wp)                :: norm
      integer                 :: n, jC

      n = size(zMat(:, :), 2)
      norm = ZERO
      do jC = 1, n
         norm = norm + dot_product(zMat(:, jC), zMat(:, jC))
      end do
      norm = sqrt(norm)
   END FUNCTION cmplx_matrix_norm

!---------------------------------------------------------------
!  cmplx_vector_norm: L2 norm of a complex vector.
!  dot_product conjugates the first arg: sum(conjg(z_i)*z_i) = sum(|z_i|^2).
!---------------------------------------------------------------
   pure FUNCTION cmplx_vector_norm(zVec) RESULT(norm)
      complex(wp), intent(in) :: zVec(:)
      real(wp)                :: norm
      norm = sqrt(dot_product(zVec, zVec))
   END FUNCTION cmplx_vector_norm

!===============================================================
!  Cross product implementations  (A x B, all type combinations)
!===============================================================

   pure FUNCTION real_vector_cross_product(A, B) RESULT(C)
      real(wp), intent(in) :: a(3), b(3)
      real(wp)             :: c(3)
      c(1) = a(2)*b(3) - a(3)*b(2)
      c(2) = a(3)*b(1) - a(1)*b(3)
      c(3) = a(1)*b(2) - a(2)*b(1)
   END FUNCTION real_vector_cross_product

   pure FUNCTION complex_vector_cross_product(A, B) RESULT(C)
      complex(wp), intent(in) :: a(3), b(3)
      complex(wp)             :: c(3)
      c(1) = a(2)*b(3) - a(3)*b(2)
      c(2) = a(3)*b(1) - a(1)*b(3)
      c(3) = a(1)*b(2) - a(2)*b(1)
   END FUNCTION complex_vector_cross_product

   pure FUNCTION complex_real_vector_cross_product(A, B) RESULT(C)
      complex(wp), intent(in) :: a(3)
      real(wp), intent(in) :: b(3)
      complex(wp)             :: c(3)
      c(1) = a(2)*b(3) - a(3)*b(2)
      c(2) = a(3)*b(1) - a(1)*b(3)
      c(3) = a(1)*b(2) - a(2)*b(1)
   END FUNCTION complex_real_vector_cross_product

   pure FUNCTION real_complex_vector_cross_product(Ain, B) RESULT(C)
      real(wp), intent(in) :: ain(3)
      complex(wp), intent(in) :: b(3)
      complex(wp)             :: c(3), a(3)
      a = cmplx(ain, 0.0)  ! promote real to complex
      c(1) = a(2)*b(3) - a(3)*b(2)
      c(2) = a(3)*b(1) - a(1)*b(3)
      c(3) = a(1)*b(2) - a(2)*b(1)
   END FUNCTION real_complex_vector_cross_product

!===============================================================
!  Miscellaneous vector utilities
!===============================================================

!---------------------------------------------------------------
!  real_unit_vector: return a unit vector in the direction of Vec.
!  Returns zero vector (unchanged) if length = 0, avoiding divide
!  by zero.
!---------------------------------------------------------------
   pure FUNCTION real_unit_vector(Vec) RESULT(uVec)
      real(wp), intent(in) :: Vec(:)
      real(wp)             :: uVec(size(Vec))
      real(wp) :: length
      length = sqrt(dot_product(Vec, Vec))
      if (length > ZERO) uVec(:) = Vec(:)/length
   END FUNCTION real_unit_vector

!---------------------------------------------------------------
!  complex_time_average: time-averaged (RMS) magnitude of a
!  complex phasor field vector z(3), = (1/sqrt(2))*|z|.
!  Uses RMS = 1/sqrt(2) from basic_header_m.
!  Result is the RMS field magnitude, suitable for time-averaged
!  power density calculations (S = |E|_rms^2 / ETA0).
!---------------------------------------------------------------
   pure FUNCTION complex_time_average(zVec) result(TimeAvg)
      complex(wp), intent(in) :: zVec(3)
      real(wp)               :: TimeAvg
      ! dot_product conjugates first arg: gives sum(|z_i|^2)
      TimeAvg = RMS*sqrt(dot_product(zVec, zVec))
   end function complex_time_average

!---------------------------------------------------------------
!  reflect_real_vector: return Vec with component i negated.
!  Used in ground-plane image theory: for a PEC ground at z=0,
!  the image of a point r=(x,y,z) is r'=(x,y,-z), obtained by
!  calling reflect_real_vector(r, 3).
!  Also used for horizontal-component sign reversal in pattern
!  image sums when the ground plane is present.
!---------------------------------------------------------------
   pure FUNCTION reflect_real_vector(Vec, i) result(outVec)
      real(wp), intent(in) :: Vec(3)
      integer, intent(in) :: i    ! component to negate (1=x, 2=y, 3=z)
      real(wp)                 :: outVec(3)
      outVec(:) = Vec(:)
      outVec(i) = -Vec(i)
   end function reflect_real_vector

!===============================================================
!  Polarimetry (legacy -- radar scattering matrix conversion)
!===============================================================

!---------------------------------------------------------------
!  Cir_Pol: convert a 2x2 linear polarization scattering matrix
!  sLin to circular polarization sCir via similarity transform:
!    sCir = (1/2) * Alpha * sLin * Alpha_inv
!  where Alpha = [[1, -j],[1, +j]] maps (Eth, Ephi) to (R, L).
!  Note: the definition of R/L circular changes sign between
!  transmitted and received waves (complex conjugate).
!  This routine is retained from the legacy radar MOM code and
!  is not used in the NeoMoM antenna solver.
!---------------------------------------------------------------
   pure SUBROUTINE Cir_Pol(sCir, sLin)
      complex(wp), intent(in) :: sLin(2, 2)
      complex(wp), intent(inout) :: sCir(2, 2)

      complex(wp) :: sTemp(2, 2), A(2, 2), A_INV(2, 2)

      A(:, 1) = [+zONE, +zONE]
      A(:, 2) = [-zIMAG, +zIMAG]

      A_INV(:, 1) = [+zONE, -zIMAG]
      A_INV(:, 2) = [+zONE, +zIMAG]

      sTemp = matmul(sLin, A_INV)
      sCir = HALF*matmul(A, sTemp)
   end subroutine

!===============================================================
!  dB conversion functions
!===============================================================

!---------------------------------------------------------------
!  dbV: voltage (field) dB conversion, 20*log10(|V|).
!  Floor: Vmin = 1e-5, giving a lower limit of -100 dB.
!---------------------------------------------------------------
   pure real(wp) function dbV(Vin)
      real(wp), intent(in) :: Vin
      real(wp) :: V, Vmin
      Vmin = 1.E-5
      V = MAX(Vin, Vmin)
      dbV = 20.0*log10(V)
   end function

!---------------------------------------------------------------
!  dbP: power dB conversion, 10*log10(P).
!  Floor: Pmin = 1e-10, giving a lower limit of -100 dB.
!---------------------------------------------------------------
   pure real(wp) function dbP(Pin)
      real(wp), intent(in) :: Pin
      real(wp) :: P, Pmin
      Pmin = 1.0E-10
      P = MAX(Pin, Pmin)
      dbP = 10.0*log10(P)
   end function

!---------------------------------------------------------------
!  zP: convert complex z from rectangular (Re,Im) to polar form
!  (|z|, angle_degrees).  Returned as a complex number for
!  compact storage: real part = magnitude, imag part = angle.
!---------------------------------------------------------------
   pure complex(wp) function zP(z)
      complex(wp), intent(in) :: z
      real(wp) ang
      ang = atan2(aimag(z), real(z))*RTOD
      zP = cmplx(abs(z), ang)
   end function

!---------------------------------------------------------------
!  zPdbV: convert complex z to (dBV magnitude, angle_degrees).
!  Real part = 20*log10(|z|), imaginary part = phase in degrees.
!  Useful for logging field or impedance values in dB-phase form.
!---------------------------------------------------------------
   pure complex(wp) function zPdbV(z)
      complex(wp), intent(in) :: z
      real(wp) ang, aMag
      ang  = atan2(aimag(z), real(z))*RTOD
      aMag = dBV(abs(z))
      zPdbV = cmplx(aMag, ang)
   end function

end module vector_and_utility_m
