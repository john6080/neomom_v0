Program neomom

!==============================================================================
!  NeoMoM — Wire Method of Moments, main driver program
!
!  Purpose:
!   Top-level orchestrator for a wire MOM EFIE solve followed by far-field
!   gain computation.  All geometry, frequency, and excitation data are read
!   from namelists; results are written to CSV and summary text files by
!   data_out, which also launches neomom_plot.
!
!  EFIE physics:
!   Z_mn = j·k·ETA0 · Σ_pq [ A_pq − (1/k²)·Φ_pq ]
!   Basis functions: triangle (rooftop) with hub current as DOF.
!   Green's function: G(R) = exp(−jkR) / (4πR)
!   Ground plane: image theory + Fresnel reflection coefficient.
!
!==============================================================================
!  PROGRAM STRUCTURE
!==============================================================================
!
!  sys%Input                          ← called ONCE before the freq loop
!   ├─ reads namelists: /runTitle/, /Ground/, /OPTIONS/
!   ├─ reads geometry  (wire primitives, node primitives)
!   └─ reads excitations (&excitation_input namelist)
!
!  Sweep mode selected by sys%sweep_mode ('pattern' or 'impedance'):
!
!  PATTERN mode (default):
!  do iFreq = 1, sys%freq%nFreq
!   ├─ Steps 1-11: mesh, solve, Zin, SWR (always run)
!   ├─ 12. pattern_3d   far-field E, gain, CSV output
!   └─ 13. data_out     summary file + launch neomom_plot
!  end do
!
!  IMPEDANCE mode (sweep=impedance or OPTIONS sweep_mode='impedance'):
!  open _Zin.csv
!  do iFreq = 1, sys%freq%nFreq
!   ├─ Steps 1-11: mesh, solve, Zin, SWR (always run)
!   └─ write one row to _Zin.csv (pattern_3d and data_out skipped)
!  end do
!  close _Zin.csv → launch neomom_Zin
!
!==============================================================================
!  NOTABLE DESIGN POINTS
!==============================================================================
!
!  Re-meshing per frequency:
!   seglengthDesired is updated each iteration so the mesh is always
!   ~nBasisPerLambda (default 40) segments per wavelength.  A new
!   Basis2(:) and Z matrix are built from scratch at each frequency.
!
!  RHS vector naming:
!   'volts' holds the right-hand side before the solve; 'cur' is
!   initialised from 'volts' and overwritten in-place by LU_Solve.
!   Using sys%cur for both avoids a separate allocation but can mislead
!   readers — it holds volts until LU_Solve returns.
!
!  Rooftop vs. pulse (MiniNEC) RHS factor:
!   For a rooftop (triangle) basis the effective excitation integral gives
!   Vrhs = 0.5 · V_source, because the average of the basis function over
!   its two half-segments is 0.5.  MiniNEC uses pulse functions, so their
!   Vrhs = V_source (twice as large).  This 2× difference is absorbed into
!   cur(iBasis) and correctly cancels in Z_in = V/I.
!
!  Multi-port power:
!   sys%PowerIn is the SUM of Pin across all excitation ports.  This is the
!   total accepted power required to normalise the far-field gain correctly
!   for phased arrays and balanced feeds.
!
!  Primary-port aliases:
!   sys%inputImpedance, sys%gamma, and sys%SWR are scalar fields carried by
!   ANTENNA_TYPE for backward compatibility with data_out and single-port
!   workflows.  They are always set to the port-1 values.  For multi-port
!   analysis, access sys%mesh%excitations(i)%Zin / gamma / SWR directly.
!
!  SWR singularity:
!   compute_gamma_SWR guards against |gamma| → 1 (open/short circuit) and
!   sets SWR = huge(real) in that case.
!
!  Impedance sweep output (_Zin.csv):
!   Columns: freq_MHz, Rin, Xin, |Zin|, Gin, Bin, |Yin|, SWR
!   Y = 1/Zin; Gin = Re(Y), Bin = Im(Y).
!   Bin zero-crossing marks resonance — key MoM validation diagnostic.
!   One file per run; all frequencies in a single CSV.
!
!==============================================================================

   use basic_header_m
   use file_m
   use frequency_m
   use antenna_system_m
   use fresnel_reflection_m
   use excitation_m
   use iso_fortran_env
   use antenna_system_m

   implicit none

   type(ANTENNA_TYPE), target :: sys           ! all solver state; see ANTENNA_TYPE

   complex(wp), allocatable :: volts(:)        ! RHS vector before solve [V]
                                               ! sys%cur holds solution after solve

   integer :: nR                               ! number of basis functions (DOF count)
   integer :: iFreq, i                         ! loop indices
   integer :: iZin                             ! Zin CSV file unit

   !------| start of main |------------------------------------------------------

   call out( compiler_version() )

   ! ---- Step 0: read input ----
   call sys%Input

   ! ---- open Zin CSV before loop if impedance sweep ----
   if (trim(sys%sweep_mode) == 'impedance') call open_Zin_csv(sys, iZin)

   ! ===========================================================================
   ! Frequency loop
   ! ===========================================================================
   do iFreq = 1, sys%freq%nFreq

      ! ---- Step 1: set wavelength and wave number for this frequency ----
      call sys%freq%Freq_Set(iFreq)

      ! ---- Step 2: target segment length = λ / nBasisPerLambda ----
      sys%mesh%seglengthDesired = sys%freq%lambda / sys%nBasisPerLambda

      ! ---- Step 3: build the mesh ----
      call sys%mesh%assemble_mesh()

      ! ---- Step 4: Fresnel reflection coefficient for this frequency ----
      call sys%mesh%Reflection_Coef%init(sys%freq%bk)

      ! ---- Step 5: fill impedance matrix ----
      call sys%mesh%matrix_fill(sys%freq%bk, sys%matrix%zBlk)

      ! ---- Step 6: LU factorisation ----
      call sys%matrix%LU_Factor()

      nR = size(sys%matrix%zBlk, 1)

      ! ---- allocate / reset RHS and solution vectors ----
      if (allocated(volts)) deallocate(volts, sys%cur)
      allocate(volts(nR), sys%cur(nR))
      volts = zZERO

      ! ---- Step 7: load RHS from excitation data ----
      call apply_excitations(sys%mesh%excitations, sys%mesh%basis2, volts)

      ! ---- Step 8: solve Z · cur = volts ----
      sys%cur = volts
      call sys%matrix%LU_Solve(sys%cur)

      ! =========================================================================
      ! Steps 9–11: per-port impedance, reflection, and total accepted power.
      ! =========================================================================
      sys%PowerIn = ZERO

      do i = 1, size(sys%mesh%excitations)
         call sys%mesh%excitations(i)%compute_Zin_Pin(sys%cur)
         call sys%mesh%excitations(i)%compute_gamma_SWR()
         call sys%mesh%excitations(i)%print_post_solve()
         sys%PowerIn = sys%PowerIn + sys%mesh%excitations(i)%Pin
      end do

      ! Primary-port aliases for single-port workflows and data_out
      sys%inputImpedance = sys%mesh%excitations(1)%Zin
      sys%gamma          = sys%mesh%excitations(1)%gamma
      sys%SWR            = sys%mesh%excitations(1)%SWR

      ! =========================================================================
      ! Steps 12-13: output — gated on sweep mode
      ! =========================================================================
      if (trim(sys%sweep_mode) == 'impedance') then

         ! Impedance sweep — append one row to Zin CSV, skip pattern
         call write_Zin_row(sys, iZin)

      else

         ! Pattern mode — full 3-D pattern and summary output
         ! ---- Step 12: 3-D far-field pattern and gain ----
         call sys%pattern_3d(sys%pat_3d)

         ! ---- Step 13: write summary output and launch neomom_plot ----
         call sys%data_out()

      end if

   end do   ! iFreq

   ! ---- close Zin CSV and launch neomom_Zin after loop ----
   if (trim(sys%sweep_mode) == 'impedance') call close_Zin_csv(sys, iZin)

contains

!==============================================================================
!  open_Zin_csv: open the impedance sweep output CSV and write the header.
!
!  Called once before the frequency loop when sweep_mode = 'impedance'.
!  File name: <cInFileBase>_Zin.csv
!
!  Header columns:
!   freq_MHz  Rin_Ohm  Xin_Ohm  Zin_Ohm  Gin_S  Bin_S  Yin_S  SWR
!
!  Y = 1/Zin; Gin = Re(Y), Bin = Im(Y).
!  Bin zero-crossing at resonance is the key MoM validation diagnostic.
!==============================================================================
   subroutine open_Zin_csv(sys, iU)
      type(ANTENNA_TYPE), intent(in) :: sys
      integer,            intent(out) :: iU

      character(512) :: cName
      integer        :: v(8)

      call date_and_time(values=v)

      write (cName, '(a,a)') trim(sys%cInFileBase), '_Zin.csv'

      open (newunit=iU, file=trim(cName), status='REPLACE')

      ! ---- header ----
      write (iU, '(a)') '# NeoMOM Impedance Sweep'
      write (iU, '(a,i4.4,2("-",i2.2),a,i2.2,2(":",i2.2))') &
         '# ', v(1), v(2), v(3), ', T', v(5), v(6), v(7)
      write (iU, '(a,a)')   '# title       : ', trim(sys%cTitle)
      write (iU, '(a,a)')   '# file        : ', trim(sys%GeoFile%cName)
      write (iU, '(a,a)')   '# ground      : ', &
         trim(sys%mesh%Reflection_Coef%cGround_Plane)
      write (iU, '(a,i0)')  '# nports      : ', size(sys%mesh%excitations)
      write (iU, '(a,i0)')  '# nfreq       : ', sys%freq%nFreq
      write (iU, '(a,f0.4)') '# fstart_MHz  : ', sys%freq%array(1)
      write (iU, '(a,f0.4)') '# fstop_MHz   : ', &
         sys%freq%array(sys%freq%nFreq)
      if (sys%freq%fstep > 0.0_wp) &
         write (iU, '(a,f0.4)') '# fstep_MHz   : ', sys%freq%fstep
      write (iU, '(a,f0.1)') '# z0_ref_Ohm  : ', 50.0
      write (iU, '(a)') '#'
      write (iU, '(a)') &
         '# freq_MHz    Rin_Ohm    Xin_Ohm    Zin_Ohm' // &
         '    Gin_S      Bin_S      Yin_S      SWR'

      write (*, '(2x,a,a)') 'Zin sweep CSV: ', trim(cName)

   end subroutine open_Zin_csv

!==============================================================================
!  write_Zin_row: append one data row to the impedance sweep CSV.
!
!  Called once per frequency inside the loop when sweep_mode = 'impedance'.
!  Requires sys%inputImpedance and sys%SWR to be set (steps 9-11 complete).
!
!  Columns: freq_MHz  Rin  Xin  |Zin|  Gin  Bin  |Yin|  SWR
!==============================================================================
   subroutine write_Zin_row(sys, iU)
      type(ANTENNA_TYPE), intent(in) :: sys
      integer,            intent(in) :: iU

      complex(wp) :: Zin, Yin
      real(wp)    :: Rin, Xin, Zin_mag
      real(wp)    :: Gin, Bin, Yin_mag

      Zin     = sys%inputImpedance
      Rin     = real(Zin,  wp)
      Xin     = aimag(Zin)
      Zin_mag = abs(Zin)

      ! Admittance Y = 1/Zin — guard against divide-by-zero
      if (Zin_mag > 0.0_wp) then
         Yin = (1.0_wp, 0.0_wp) / Zin
      else
         Yin = (0.0_wp, 0.0_wp)
      end if

      Gin     = real(Yin,  wp)
      Bin     = aimag(Yin)
      Yin_mag = abs(Yin)

      write (iU, '(8g14.6)') &
         sys%freq%freq_mhz, &
         Rin, Xin, Zin_mag, &
         Gin, Bin, Yin_mag, &
         sys%SWR

   end subroutine write_Zin_row

!==============================================================================
!  close_Zin_csv: close the impedance sweep CSV and launch neomom_Zin.
!
!  Called once after the frequency loop when sweep_mode = 'impedance'.
!  Launches neomom_Zin non-blocking (wait=.false.) if sys%bPlot = .TRUE.
!  Use plot=.false. on command line to suppress the launch for batch runs.
!==============================================================================
   subroutine close_Zin_csv(sys, iU)
      type(ANTENNA_TYPE), intent(in) :: sys
      integer,            intent(in) :: iU

      character(512) :: cName, cCmd

      write (cName, '(a,a)') trim(sys%cInFileBase), '_Zin.csv'

      close (iU)
      write (*, '(2x,a,a)') 'Zin sweep complete: ', trim(cName)

      ! ---- launch neomom_Zin (non-blocking) ----
      if (sys%bPlot) then
         cCmd = 'neomom_Zin  '
         call execute_command_line( &
            trim(cCmd)//' '//trim(cName), wait=.false.)
      else
         write (*, '(2x,a)') 'Plot suppressed (plot=.false.)'
      end if

   end subroutine close_Zin_csv

END Program neomom