Program neomom

!==============================================================================
!  NeoMoM — Wire Method of Moments, main driver program
!
!  Purpose:
!   Top-level orchestrator for a wire MOM EFIE solve followed by far-field
!   gain computation.  All geometry, frequency, and excitation data are read
!   from namelists; results are written to CSV and summary text files by
!   data_out, which also launches plot_neomom.
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
!  do iFreq = 1, sys%freq%nFreq
!   │
!   ├─ 1. freq%Freq_Set(iFreq)        set λ, bk = 2πf/c for this frequency
!   ├─ 2. mesh%seglengthDesired       = λ / nBasisPerLambda  (re-mesh per freq)
!   ├─ 3. mesh%assemble_mesh()        build Segs, Nodes, Basis2(:)
!   ├─ 4. Reflection_Coef%init(bk)   Fresnel ε_eff for this frequency
!   ├─ 5. mesh%matrix_fill(bk, zBlk)  fill upper triangle of Z [nBasis×nBasis]
!   ├─ 6. matrix%LU_Factor()          factor (MKL Bunch-Kaufman or pure LU)
!   ├─ 7. apply_excitations → volts   RHS(iBasis) = zVolts for each port
!   ├─ 8. LU_Solve(cur)               cur ← Z⁻¹·volts   [A, complex]
!   ├─ 9. per-port: compute_Zin_Pin, compute_gamma_SWR, print_post_solve
!   ├─ 10. sys%PowerIn                = sum of Pin across all ports
!   ├─ 11. primary-port aliases       inputImpedance, gamma, SWR ← port 1
!   ├─ 12. pattern_3d                 far-field E, gain, CSV output
!   └─ 13. data_out                   summary file + launch plot_neomom
!
!  end do
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
!==============================================================================

   use basic_header_m
   use file_m
   use frequency_m
   use antenna_system_m
   use fresnel_reflection_m
   use excitation_m

   implicit none

   type(ANTENNA_TYPE), target :: sys           ! all solver state; see ANTENNA_TYPE

   complex(wp), allocatable :: volts(:)        ! RHS vector before solve [V]
                                               ! sys%cur holds solution after solve

   integer :: nR                               ! number of basis functions (DOF count)
   integer :: iFreq, i                         ! loop indices

   !------| start of main |------------------------------------------------------

   ! ---- Step 0: read input ----
   ! Input reads namelists (/runTitle/, /Ground/, /OPTIONS/), mesh geometry
   ! (wire primitives + node primitives), and excitations (&excitation_input).
   ! Called ONCE outside the frequency loop; geometry is fixed across freqs.
   call sys%Input

   ! ===========================================================================
   ! Frequency loop — all mesh and matrix operations repeat per frequency
   ! because the segment length and basis functions depend on wavelength.
   ! ===========================================================================
   do iFreq = 1, sys%freq%nFreq

      ! ---- Step 1: set wavelength and wave number for this frequency ----
      ! Freq_Set assigns: freq_mhz, lambda = c/f, bk = 2π/lambda [1/m]
      call sys%freq%Freq_Set(iFreq)

      ! ---- Step 2: target segment length = λ / nBasisPerLambda ----
      ! Default nBasisPerLambda = 40 → ~λ/40 segments.
      ! assemble_mesh subdivides each wire primitive to honour this length.
      sys%mesh%seglengthDesired = sys%freq%lambda / sys%nBasisPerLambda

      ! ---- Step 3: build the mesh ----
      ! Populates: Segs(:), Nodes(:), Basis2(:), connectivity, node_primitives.
      ! Re-called each frequency so the DOF count may differ between iterations.
      call sys%mesh%assemble_mesh()

      ! ---- Step 4: Fresnel reflection coefficient for this frequency ----
      ! init(bk) computes ε_eff = ε_r − j·σ·η0/bk from the ground parameters
      ! read by Input.  (Note: current code uses σ/bk; η0 factor may be missing
      ! — see Fresnel_Reflection_m documentation for the dimensional check.)
      call sys%mesh%Reflection_Coef%init(sys%freq%bk)

      ! ---- Step 5: fill impedance matrix ----
      ! zfill_m fills the UPPER TRIANGLE only (symmetric EFIE matrix).
      ! If USE_MKL=.FALSE. the pure-Fortran LU path must copy upper→lower
      ! before factoring — this is handled inside matrix_fill / LU_Factor.
      call sys%mesh%matrix_fill(sys%freq%bk, sys%matrix%zBlk)

      ! ---- Step 6: LU factorisation ----
      ! MKL path: csytrf (Bunch-Kaufman symmetric factorisation).
      ! Pure Fortran path: partial-pivot LU after symmetrisation.
          
      call sys%matrix%LU_Factor()

      nR = size(sys%matrix%zBlk, 1)   ! nBasis for this frequency
      
      ! ---- allocate / reset RHS and solution vectors ----
      ! Both volts (RHS) and cur (solution, allocated inside ANTENNA_TYPE)
      ! are released and re-allocated because nR may change with frequency.
      if (allocated(volts)) deallocate(volts, sys%cur)
      allocate(volts(nR), sys%cur(nR))
      volts = zZERO

      ! ---- Step 7: load RHS from excitation data ----
      ! apply_excitations sets volts(iBasis) = zVolts for each port.
      ! Accumulates (+=) to support multiple simultaneous sources.
      ! Precondition: find_feed_node and find_basis_ID were called in Input.
      call apply_excitations(sys%mesh%excitations, sys%mesh%basis2, volts)

      ! ---- Step 8: solve Z · cur = volts ----
      ! sys%cur is initialised to volts then overwritten in-place by LU_Solve.
      ! After return, sys%cur(m) = current [A] at basis hub m.
      sys%cur = volts
      call sys%matrix%LU_Solve(sys%cur)

      ! =========================================================================
      ! Steps 9–11: per-port impedance, reflection, and total accepted power.
      !
      ! Each excitation carries its own Zin, Pin, gamma, SWR (see EXCITATION_TYPE).
      ! compute_Zin_Pin   : Zin = zVolts/I_hub;  Pin = 0.5 Re(V·I*)
      ! compute_gamma_SWR : gamma = (Zin−Z0_ref)/(Zin+Z0_ref); SWR from |gamma|
      ! print_post_solve  : formatted port summary to stdout
      !
      ! sys%PowerIn = sum of Pin across all ports (used by pattern_3d for gain).
      ! Primary-port aliases (inputImpedance, gamma, SWR) set from port 1 for
      ! backward compatibility with data_out.
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

      ! ---- Step 12: 3-D far-field pattern and gain ----
      ! pattern_3d:
      !  (a) builds adaptive theta/phi grid (step ~ bw/10, snapped to DIV360)
      !  (b) calls pattern_v2 for exact radiation integrals at each angle
      !  (c) calls power_check (trapezoidal phi integration for P_rad)
      !  (d) computes G_theta, G_phi, G_total [linear]; finds peak angles
      !  (e) normalises Er → Er/sqrt(P_in) for CSV output
      !  (f) writes .csv file (plot_neomom recovers gain as FOURPI/(2*ETA0)*|Er|²)
      call sys%pattern_3d(sys%pat_3d)

      ! ---- Step 13: write summary output and launch plot_neomom ----
      ! data_out writes a .txt summary (Z_in, SWR, gain, grid params) and
      ! calls execute_command_line('neomom_plot <csv>', wait=.false.).
      call sys%data_out()

   end do   ! iFreq

contains

END Program neomom
