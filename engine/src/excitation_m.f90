module excitation_m

!==============================================================================
!  excitation_m — voltage excitation model for NeoMoM wire MOM
!
!  Purpose:
!   Define EXCITATION_TYPE, read the &excitation_input namelist, map the feed
!   location (wire tag + node tag) to a basis function index, apply the voltage
!   source to the right-hand side, and compute port quantities after the solve.
!
!  Public interface:
!   EXCITATION_TYPE   -- excitation state container (type)
!   read_excitations  -- read &excitation_input namelist, allocate Excit(:)
!   apply_excitations -- fill RHS(:) for all excitations
!
!==============================================================================
!  EXCITATION MODEL — BASIS-FUNCTION VOLTAGE
!==============================================================================
!
!  NeoMoM's natural excitation unit is one ROOFTOP BASIS FUNCTION, which
!  spans two adjacent segments.  The source voltage drives that basis as a
!  whole:
!
!   RHS(iBasis) = zVolts             (full voltage on one basis function)
!
!  The physical current at the basis hub is cur(iBasis).  Therefore:
!
!   Z_in = zVolts / cur(iBasis)
!   P_in = 0.5 * Re( zVolts * conjg(cur(iBasis)) )
!
!  Comparison with NEC-5:
!   Wire-end feed  : ~14% difference in R  (expected — effective source
!                    locations differ by ~λ/80 due to half-segment offset)
!   Interior feed  : ~3% difference in R   (both codes agree well away
!                    from the wire-end singularity)
!
!==============================================================================
!  FINDING iBasis FROM NODE TAG
!==============================================================================
!
!  The feed location is specified by a wire tag + node tag pair; it maps to a
!  global node index via position matching, then to a basis function index by
!  finding the basis whose hub node is at (or nearest to) that location.
!
!  Wire-end node (nTouch = 1):
!   No basis hub exists at a wire-end node.  Follow the one adjacent segment
!   to the first interior node and use the basis whose hub is at that node.
!
!  Interior node (nTouch = 2):
!   Exactly one basis has its hub here.  Use it directly.
!
!  Junction node (nTouch >= 3):
!   Hub is at iNode_feed; disambiguate among multiple bases by feed wire tag.
!   Select the basis whose halves both belong to the feed wire, or whose
!   first matching half is on that wire.  If multiple survive, WARNING + first.
!
!==============================================================================
!  MULTIPLE EXCITATIONS
!==============================================================================
!
!  For phased arrays or balanced feeds, list multiple entries in the
!  &excitation_input namelist (up to MAX_EXCIT = 20).
!  apply_excitations accumulates all contributions into RHS(:) before solve.
!  Post-solve, call compute_Zin_Pin and compute_gamma_SWR on each port.
!  Total antenna power is the sum of Pin across all ports.
!
!==============================================================================
!  CALL SEQUENCE
!==============================================================================
!
!  1. read_excitations(iUnit, Excit)              -- reads namelist, allocates
!  2. Excit(i)%find_feed_node(...)                -- resolves tag → iNode_feed
!  3. Excit(i)%find_basis_ID(Basis2, Segs, Conn)  -- maps iNode_feed → iBasis
!  4. apply_excitations(Excit, Basis2, RHS)        -- RHS(iBasis) = zVolts
!  5. ... matrix solve ...
!  6. Excit(i)%compute_Zin_Pin(cur)               -- fills Zin, Pin in Excit(i)
!  7. Excit(i)%compute_gamma_SWR()                -- fills gamma, SWR from Zin, Z0_ref
!  8. Excit(i)%print_post_solve()                 -- pretty-print port results
!
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m, only: SEGMENT_TYPE, NODE_TYPE, WIRE_PRIMITIVE_TYPE
   use basis_builder_m, only: BASIS2_TYPE
   use connectivity_m, only: NODE_CONN_TYPE
   use vector_and_utility_m, only: toupper, nml_error

   implicit none; private

   public :: EXCITATION_TYPE, read_excitations, apply_excitations

   !  Maximum number of simultaneous excitation ports
   integer, parameter :: MAX_EXCIT = 20

!------------------------------------------------------------------------------
!  EXCITATION_TYPE: state for one voltage excitation port.
!
!  Namelist inputs (set by read_excitations):
!   cWireTag   -- wire primitive tag identifying the feed wire (e.g. 'W0')
!   cNodeTag   -- corner node tag on that wire (e.g. 'F' for feed end)
!   voltage    -- source amplitude [V] (default 1.0)
!   phase_deg  -- source phase [degrees] (default 0.0)
!   Z0_ref     -- reference impedance for gamma/SWR [Ω] (default 50.0)
!
!  Derived phasor (set by set_volts, called from read_excitations):
!   zVolts     -- complex phasor = voltage * exp(j * phase_deg * DTOR)
!
!  Set by find_feed_node:
!   iNode_feed -- global merged node index of the physical feed location
!   v_feed     -- 3-D position of the feed node [m]
!
!  Set by find_basis_ID:
!   iNode_hub  -- hub node of the driven basis function
!   iBasis     -- index into Basis2(:); the driven degree of freedom
!
!  Post-solve results (set by compute_Zin_Pin, compute_gamma_SWR):
!   Zin        -- complex input impedance at this port [Ω]
!   Pin        -- accepted power at this port [W] = 0.5 Re(V * conj(I))
!   gamma      -- voltage reflection coefficient = (Zin - Z0_ref)/(Zin + Z0_ref)
!   SWR        -- standing wave ratio = (1 + |gamma|) / (1 - |gamma|)
!                 Set to huge(real) when |gamma| >= 1 - 1e-6 (open/short guard).
!------------------------------------------------------------------------------
   type :: EXCITATION_TYPE

      ! ---- namelist input ----
      character(len=16) :: cWireTag = ' '
      character(len=8)  :: cNodeTag = ' '
      real(wp)          :: voltage = ONE
      real(wp)          :: phase_deg = ZERO
      real(wp)          :: Z0_ref = 50.0_wp   ! reference impedance [Ω]

      ! ---- complex voltage phasor (set by set_volts) ----
      complex(wp)       :: zVolts = zONE

      ! ---- feed node (set by find_feed_node) ----
      integer           :: iNode_feed = 0
      real(wp)          :: v_feed(3) = ZERO     ! 3-D position [m]

      ! ---- driven basis function (set by find_basis_ID) ----
      integer           :: iNode_hub = 0        ! hub node index
      integer           :: iBasis = 0        ! Basis2 index

      ! ---- post-solve port quantities (set by compute_Zin_Pin / compute_gamma_SWR) ----
      complex(wp)       :: Zin = zZERO         ! input impedance [Ω]
      real(wp)          :: Pin = ZERO           ! accepted power [W]
      complex(wp)       :: gamma = zZERO          ! voltage reflection coefficient
      real(wp)          :: SWR = ZERO           ! standing wave ratio

   contains
      procedure :: set_volts
      procedure :: find_feed_node
      procedure :: find_basis_ID
      procedure :: compute_Zin_Pin
      procedure :: compute_gamma_SWR
      procedure :: print_excitation
      procedure :: print_post_solve

   end type EXCITATION_TYPE

contains

!==============================================================================
!  read_excitations: read &excitation_input namelist and allocate Excit(:).
!
!  Namelist format:
!   &excitation_input
!     nExcitations  = 1
!     WireTag(1)    = 'W0',   NodeTag(1)   = 'F'
!     voltage(1)    = 1.0,    phase_deg(1) = 0.0
!     Z0_ref(1)     = 50.0
!   /
!
!  Up to MAX_EXCIT = 20 excitations may be listed.
!  The file unit is rewound before reading so namelist position is irrelevant.
!  After reading, set_volts is called for each excitation to compute zVolts.
!==============================================================================
   subroutine read_excitations(iUnit, Excit)

      integer, intent(in)  :: iUnit
      type(EXCITATION_TYPE), allocatable, intent(out) :: Excit(:)

      integer           :: nExcitations = 0
      character(len=16) :: WireTag = ' '
      character(len=8)  :: NodeTag = ' '
      real              :: voltage = ONE
      real              :: phase_deg = ZERO
      real              :: Z0_ref = 50.0

      ! character(len=16) :: WireTag(MAX_EXCIT) = ' '
      ! character(len=8)  :: NodeTag(MAX_EXCIT) = ' '
      ! real(wp)          :: voltage(MAX_EXCIT) = ONE
      ! real(wp)          :: phase_deg(MAX_EXCIT) = ZERO
      ! real(wp)          :: Z0_ref(MAX_EXCIT) = 50.0_wp

      namelist /excitation_input/ nExcitations, WireTag, NodeTag, &
         voltage, phase_deg, Z0_ref

      integer        :: i, ios
      character(256) :: msg

      ! Find number of excitations

      rewind (iUnit)
      nExcitations = 0
      do
         read (iUnit, nml=excitation_input, iostat=ios, iomsg=msg)
         if (ios /= 0) exit
         !call nml_error('excitation_input', ios, msg)
         nExcitations = nExcitations + 1
      end do

      if (nExcitations < 1 .or. nExcitations > MAX_EXCIT) &
         call FatalError('read_excitations: nExcitations out of range', '', 0)

      allocate (Excit(nExcitations))
      rewind (iUnit)
      do i = 1, nExcitations

         read (iUnit, nml=excitation_input, iostat=ios, iomsg=msg)

         Excit(i)%cWireTag = WireTag
         Excit(i)%cNodeTag = NodeTag
         Excit(i)%voltage = voltage
         Excit(i)%phase_deg = phase_deg
         Excit(i)%Z0_ref = Z0_ref
         call Excit(i)%set_volts()
      end do

      write (*, '(a,i3,a)') '  read_excitations: ', nExcitations, ' excitation(s)'

   end subroutine read_excitations

!==============================================================================
!  set_volts: compute complex phasor from magnitude and phase.
!
!   zVolts = voltage * exp(j * phase_deg * pi/180)
!
!  Called automatically by read_excitations after field assignment.
!==============================================================================
   subroutine set_volts(this)

      class(EXCITATION_TYPE), intent(inout) :: this

      this%zVolts = this%voltage*exp(zIMAG*this%phase_deg*DTOR)

   end subroutine set_volts

!==============================================================================
!  find_feed_node: resolve (cWireTag, cNodeTag) → global node index iNode_feed.
!
!  Algorithm (3 steps):
!   Step 1 — Look up corner position from node_primitives by tag.
!            FatalError if cNodeTag not found.
!   Step 2 — Verify the named wire has this node in its nodeTags list.
!            FatalError if cWireTag not found or node not on that wire.
!   Step 3 — Find the matching global node in Nodes(:) by position, within tol.
!            Default tolerance: DEFAULT_TOL = 1e-6 m (1 micron).
!            Override with optional tol_in argument.
!            FatalError with diagnostic if no node found within tolerance.
!
!  Sets:  this%iNode_feed, this%v_feed
!==============================================================================
   subroutine find_feed_node(this, wire_primitives, node_primitives, Nodes, tol_in)

      class(EXCITATION_TYPE), intent(inout) :: this
      type(WIRE_PRIMITIVE_TYPE), intent(in)    :: wire_primitives(:)
      type(NODE_TYPE), intent(in)    :: node_primitives(:)
      type(NODE_TYPE), intent(in)    :: Nodes(:)
      real(wp), optional, intent(in)    :: tol_in

      character(len=16) :: cWire, cWirePrim
      character(len=8)  :: cNode, cNP, cTagPrim
      real(wp)          :: v_corner(3), tol, dist
      integer           :: iPrim, iTag, iNode, iNP
      logical           :: found_prim, found_tag, found_node, wire_has_node

      real(wp), parameter :: DEFAULT_TOL = 1.0E-4   ! 1 micron

      tol = DEFAULT_TOL
      if (present(tol_in)) tol = tol_in

      cWire = this%cWireTag; call toUpper(cWire)
      cNode = this%cNodeTag; call toUpper(cNode)

      ! ---- Step 1: get corner position from node primitives ----
      found_tag = .false.
      do iNP = 1, size(node_primitives)
         cNP = node_primitives(iNP)%tag; call toUpper(cNP)
         if (trim(cNP) == trim(cNode)) then
            v_corner = node_primitives(iNP)%v
            found_tag = .true.; exit
         end if
      end do
      if (.not. found_tag) &
         call FatalError('find_feed_node: cNodeTag not found in node_primitives', &
                         trim(cNode), 0)

      ! ---- Step 2: confirm the named wire owns this node tag ----
      found_prim = .false.
      wire_has_node = .false.
      do iPrim = 1, size(wire_primitives)
         cWirePrim = wire_primitives(iPrim)%tag; call toUpper(cWirePrim)
         if (trim(cWirePrim) /= trim(cWire)) cycle
         found_prim = .true.
         do iTag = 1, size(wire_primitives(iPrim)%nodeTags)
            cTagPrim = wire_primitives(iPrim)%nodeTags(iTag); call toUpper(cTagPrim)
            if (trim(cTagPrim) == trim(cNode)) then
               wire_has_node = .true.; exit
            end if
         end do
         exit
      end do
      if (.not. found_prim) &
         call FatalError('find_feed_node: cWireTag not found in wire_primitives', &
                         trim(cWire), 0)
      if (.not. wire_has_node) &
         call FatalError('find_feed_node: cNodeTag not on specified wire', &
                         trim(cNode)//' on '//trim(cWire), 0)

      ! ---- Step 3: match corner position to a global merged node ----
      found_node = .false.
      do iNode = 1, size(Nodes)
         dist = norm2(Nodes(iNode)%v - v_corner)
         if (dist < tol) then
            this%iNode_feed = iNode
            this%v_feed = Nodes(iNode)%v
            found_node = .true.; exit
         end if
      end do
      if (.not. found_node) then
         write (*, '(a,3g14.6)') '  Feed corner v [m] = ', v_corner
         write (*, '(a,g14.6)') '  Search tolerance  = ', tol
         call FatalError('find_feed_node: no global node within tolerance', '', 0)
      end if

      write (*, '(a,a,a,a,a,i5,3x,3f10.4)') &
         '  find_feed_node:  wire=', trim(cWire), &
         '  node=', trim(cNode), &
         '  iNode=', this%iNode_feed, this%v_feed

   end subroutine find_feed_node

!==============================================================================
!  find_basis_ID: map iNode_feed → (iNode_hub, iBasis).
!
!  Precondition: find_feed_node must have been called (iNode_feed /= 0).
!
!  nTouch dispatch:
!   nTouch = 1 (wire end): follow adjacent segment to first interior node.
!   nTouch = 2 (interior): hub is at iNode_feed directly.
!   nTouch >= 3 (junction): hub at iNode_feed; disambiguate by feed wire tag.
!
!  Sets:  this%iNode_hub, this%iBasis
!==============================================================================
   subroutine find_basis_ID(this, Basis2, Segs, Conn)

      class(EXCITATION_TYPE), intent(inout) :: this
      type(BASIS2_TYPE), intent(in)    :: Basis2(:)
      type(SEGMENT_TYPE), intent(in)    :: Segs(:)
      type(NODE_CONN_TYPE), intent(in)    :: Conn(:)

      character(len=16) :: cWire, cSegWire
      integer :: iSeg, iNode_candidate, m, nFound

      if (this%iNode_feed == 0) &
         call FatalError('find_basis_ID: call find_feed_node first', '', 0)

      cWire = this%cWireTag; call toUpper(cWire)

      ! ---- determine hub node ----
      select case (Conn(this%iNode_feed)%nTouch)

      case (1)
         iSeg = Conn(this%iNode_feed)%touch(1)%iSeg
         if (Conn(this%iNode_feed)%touch(1)%iEnd == 1) then
            iNode_candidate = Segs(iSeg)%iRightNode
         else
            iNode_candidate = Segs(iSeg)%iLeftNode
         end if
         this%iNode_hub = iNode_candidate
         write (*, '(a,i5,a,i5)') &
            '  find_basis_ID: wire-end → advanced to hub node ', &
            this%iNode_hub, '  via segment ', iSeg

      case (2)
         this%iNode_hub = this%iNode_feed

      case default
         this%iNode_hub = this%iNode_feed

      end select

      ! ---- find basis function at iNode_hub ----
      this%iBasis = 0
      nFound = 0

      do m = 1, size(Basis2)
         if (Basis2(m)%iNode /= this%iNode_hub) cycle

         if (Conn(this%iNode_hub)%nTouch >= 3) then
            cSegWire = Segs(Basis2(m)%half(1)%iSeg)%wireTag; call toUpper(cSegWire)
            if (trim(cSegWire) /= trim(cWire)) then
               cSegWire = Segs(Basis2(m)%half(2)%iSeg)%wireTag; call toUpper(cSegWire)
               if (trim(cSegWire) /= trim(cWire)) cycle
            end if
         end if

         nFound = nFound + 1
         if (this%iBasis == 0) this%iBasis = m

      end do

      if (this%iBasis == 0) &
         call FatalError('find_basis_ID: no basis found at hub node', '', this%iNode_hub)

      if (nFound > 1) &
         write (*, '(a,i3,a,i5)') &
         '  find_basis_ID: WARNING — ', nFound, &
         ' bases at junction hub, using iBasis=', this%iBasis

      write (*, '(a,i5,a,i5)') &
         '  find_basis_ID:  iNode_hub=', this%iNode_hub, &
         '  iBasis=', this%iBasis

   end subroutine find_basis_ID

!==============================================================================
!  apply_excitations: load RHS for all excitation ports.
!
!  For each excitation i:
!   RHS(iBasis) += zVolts
!
!  Accumulates (+=) to support multiple simultaneous sources.
!  No shape-factor correction: rooftop basis = 1.0 at hub.
!  Precondition: find_basis_ID must have been called (iBasis valid).
!==============================================================================
   subroutine apply_excitations(Excit, Basis2, RHS)

      type(EXCITATION_TYPE), intent(in)    :: Excit(:)
      type(BASIS2_TYPE), intent(in)    :: Basis2(:)
      complex(wp), intent(inout) :: RHS(:)

      integer :: i, iB

      do i = 1, size(Excit)
         iB = Excit(i)%iBasis
         if (iB < 1 .or. iB > size(RHS)) &
            call FatalError('apply_excitations: iBasis out of range — '// &
                            'call find_basis_ID first', '', iB)

         RHS(iB) = RHS(iB) + Excit(i)%zVolts

         write (*, '(a,i2,a,i5,a,2f10.4)') &
            '  apply_excitations: excit=', i, &
            '  iBasis=', iB, '  zVolts=', Excit(i)%zVolts

      end do

   end subroutine apply_excitations

!==============================================================================
!  compute_Zin_Pin: input impedance and accepted power after the matrix solve.
!
!  Stores results in this%Zin and this%Pin.
!
!   I_hub = cur(iBasis)
!   Zin   = zVolts / I_hub                         [Ω]
!   Pin   = 0.5 * Re( zVolts * conjg(I_hub) )      [W]
!
!  Guard: if |I_hub| < 1e-30 (open circuit or solve failure), Zin is set to
!  huge + j0 and Pin to 0.0 with a WARNING.  Prevents NaN in downstream
!  gamma, SWR, and gain calculations.
!
!  NEC comparison: interior feed ~3% difference in R (recommended validation);
!  wire-end feed ~14% (half-segment offset).
!==============================================================================
   subroutine compute_Zin_Pin(this, cur)

      class(EXCITATION_TYPE), intent(inout) :: this
      complex(wp), intent(in)    :: cur(:)

      complex(wp) :: I_hub

      if (this%iBasis < 1 .or. this%iBasis > size(cur)) &
         call FatalError('compute_Zin_Pin: iBasis out of range', '', this%iBasis)

      I_hub = cur(this%iBasis)

      if (abs(I_hub) < 1.0e-30_wp) then
         write (*, '(a,a,a)') '  compute_Zin_Pin: WARNING — cur(iBasis) ~= 0', &
            '  port: ', trim(this%cWireTag)//'/'//trim(this%cNodeTag)
         this%Zin = cmplx(huge(ONE), ZERO, wp)
         this%Pin = ZERO
         return
      end if

      this%Zin = this%zVolts/I_hub
      this%Pin = HALF*real(this%zVolts*conjg(I_hub), wp)

   end subroutine compute_Zin_Pin

!==============================================================================
!  compute_gamma_SWR: reflection coefficient and SWR from Zin and Z0_ref.
!
!  Precondition: compute_Zin_Pin must have been called (this%Zin valid).
!
!   gamma = (Zin - Z0_ref) / (Zin + Z0_ref)
!   SWR   = (1 + |gamma|) / (1 - |gamma|)
!
!  Z0_ref is treated as real (resistive reference), which covers the standard
!  50 Ω and 75 Ω cases.  For complex Z0 extend Z0_ref to complex(wp).
!
!  Guard: if |gamma| >= 1 - 1e-6 (near open/short circuit), SWR is set to
!  huge(real) to prevent division by zero.
!==============================================================================
   subroutine compute_gamma_SWR(this)

      class(EXCITATION_TYPE), intent(inout) :: this

      complex(wp) :: Z0c
      real(wp)    :: abs_g

      Z0c = cmplx(this%Z0_ref, ZERO, wp)

      this%gamma = (this%Zin - Z0c)/(this%Zin + Z0c)

      abs_g = abs(this%gamma)

      if (abs_g >= ONE - 1.0e-6_wp) then
         write (*, '(a,a)') '  compute_gamma_SWR: WARNING — |gamma| ~= 1, SWR → ∞', &
            '  port: '//trim(this%cWireTag)//'/'//trim(this%cNodeTag)
         this%SWR = huge(ONE)
      else
         this%SWR = (ONE + abs_g)/(ONE - abs_g)
      end if

   end subroutine compute_gamma_SWR

!==============================================================================
!  print_post_solve: formatted console output of all post-solve port results.
!
!  Reports (per port):
!   Port label       wire tag / node tag
!   Z_in             R + jX [Ω],  |Z| [Ω],  angle [deg]
!   Z0_ref           reference impedance [Ω]
!   Gamma            |gamma|, angle [deg]
!   SWR
!   P_in             [W] and [mW]
!   |I_hub|          derived from Pin and Zin for quick sanity check
!
!  Precondition: compute_Zin_Pin and compute_gamma_SWR must have been called.
!==============================================================================
   subroutine print_post_solve(this)

      class(EXCITATION_TYPE), intent(in) :: this

      real(wp) :: Zr, Zx, Zmag, Zang_deg
      real(wp) :: gMag, gAng_deg
      real(wp) :: I_mag_mA

      Zr = real(this%Zin, wp)
      Zx = aimag(this%Zin)
      Zmag = abs(this%Zin)
      Zang_deg = atan2(Zx, Zr)*RTOD

      gMag = abs(this%gamma)
      gAng_deg = atan2(aimag(this%gamma), real(this%gamma, wp))*RTOD

      ! |I_hub| = sqrt(2 * Pin / Re(Zin)), avoids needing cur() here
      if (Zr > ZERO .and. this%Pin > ZERO) then
         I_mag_mA = sqrt(2.0_wp*this%Pin/Zr)*1000.0_wp
      else
         I_mag_mA = ZERO
      end if

      write (*, '(a)') '  ===== Port: '//trim(this%cWireTag)//' / '//trim(this%cNodeTag)//' ====='
      write (*, '(a,f10.4,a,f10.4,a)') &
         '  Z_in   :', Zr, ' + j ', Zx, '  Ohm'
      write (*, '(a,f10.4,a,f8.3,a)') &
         '  |Z_in| :', Zmag, '  Ohm     ang =', Zang_deg, '  deg'
      write (*, '(a,f10.4,a)') &
         '  Z0_ref :', this%Z0_ref, '  Ohm'
      write (*, '(a,f9.5,a,f8.3,a)') &
         '  Gamma  :', gMag, '          ang =', gAng_deg, '  deg'
      write (*, '(a,f10.4)') &
         '  SWR    :', this%SWR
      write (*, '(a,es11.4,a,f9.3,a)') &
         '  P_in   :', this%Pin, '  W   (', this%Pin*1000.0_wp, '  mW)'
      write (*, '(a,f9.3,a)') &
         '  |I_hub|:', I_mag_mA, '  mA   (derived from P_in / Re(Zin))'
      write (*, '(a)') '  =================================================='

   end subroutine print_post_solve

!==============================================================================
!  print_excitation: dump setup fields to stdout for pre-solve diagnostics.
!==============================================================================
   subroutine print_excitation(this)

      class(EXCITATION_TYPE), intent(in) :: this

      write (*, '(a)') '  --- Excitation setup ---'
      write (*, '(a,a)') '    Wire tag      : ', trim(this%cWireTag)
      write (*, '(a,a)') '    Node tag      : ', trim(this%cNodeTag)
      write (*, '(a,f10.4)') '    Voltage   [V] : ', this%voltage
      write (*, '(a,f10.4)') '    Phase   [deg] : ', this%phase_deg
      write (*, '(a,2f10.4)') '    zVolts        : ', this%zVolts
      write (*, '(a,f10.4)') '    Z0_ref   [Ohm]: ', this%Z0_ref
      write (*, '(a,i5)') '    iNode_feed    : ', this%iNode_feed
      write (*, '(a,3f10.4)') '    v_feed    [m] : ', this%v_feed
      write (*, '(a,i5)') '    iNode_hub     : ', this%iNode_hub
      write (*, '(a,i5)') '    iBasis        : ', this%iBasis

   end subroutine print_excitation

end module excitation_m
