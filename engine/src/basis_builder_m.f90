module basis_builder_m

!==============================================================================
!  basis_builder_m
!
!  Purpose:
!   Construct rooftop (triangle) basis functions from the node connectivity
!   table produced by connectivity_m.  Each basis function (BASIS2_TYPE)
!   represents one unknown current coefficient in the EFIE system.
!
!  Output of this module:
!   Basis(:) array of BASIS2_TYPE — direct input to zfill_m.f90 (Z-matrix fill)
!   and excitation_m.f90 (RHS / feed vector).
!
!==============================================================================
!  BASIS FUNCTION DEFINITION
!==============================================================================
!
!  A rooftop basis function B centred at node n has two halves:
!    half(1) : the "positive-divergence" half  (charge source side)
!    half(2) : the "negative-divergence" half  (charge sink side)
!
!  For half h on segment s at node n, the vector basis function is:
!
!    f_h(x)  =  effSign_h  *  scalar_h(x)  *  Segs(s)%uHat
!
!  where x is measured from Segs(s)%iLeftNode along the segment, and:
!
!    scalar(x, iEnd=2) = x / L          node is iRightNode, ascending  0 → 1
!    scalar(x, iEnd=1) = (L - x) / L   node is iLeftNode,  descending 1 → 0
!
!  The divergence of each half is constant over the segment:
!
!    div_h = effSign_h * naturalSign_h / L      [1/m]
!
!  where:
!    naturalSign = +1  if iEnd==2  (ascending  → positive divergence)
!    naturalSign = -1  if iEnd==1  (descending → negative divergence)
!
!  Compact formula:  naturalSign = 2*iEnd - 3   (iEnd=1 → -1,  iEnd=2 → +1)
!
!  effSign_h is chosen so that:
!    half(1) always has div_h > 0   →   effSign =  naturalSign
!    half(2) always has div_h < 0   →   effSign = -naturalSign
!
!  Consequence: |div_h| = 1/L always.  Only the sign differs between the two
!  halves.  This works for any segment orientation, removing the need for the
!  caller to track segment storage directions.
!
!  Four cases of seg_touch_to_half (verified algebraically):
!    iEnd=2, wantPositive=T  →  effSign=+1, div=+1/L  (natural, no flip needed)
!    iEnd=2, wantPositive=F  →  effSign=-1, div=-1/L  (flipped)
!    iEnd=1, wantPositive=T  →  effSign=-1, div=+1/L  (flipped to force positive)
!    iEnd=1, wantPositive=F  →  effSign=+1, div=-1/L  (natural, no flip needed)
!
!==============================================================================
!  JUNCTION STRATEGY — "anchor + partners"
!==============================================================================
!
!  At a node with N touching segments there are N-1 independent current DOFs
!  (KCL removes one: the sum of all outgoing currents = 0).
!
!  Procedure (basis_at_node):
!    1. Choose one segment as the "anchor" (always becomes half(1), +div).
!       Prefer a segment with iEnd==2 (natural positive div → effSign=+1,
!       simpler arithmetic).  If all segments have iEnd==1, use the first;
!       effSign=-1 will be applied to flip the divergence sign.
!    2. Pair the anchor with each of the remaining N-1 segments as half(2)
!       (negative div).
!    → Produces exactly N-1 basis functions regardless of N or of how the
!      segments happen to be stored.
!
!  Examples:
!    Simple node (N=2):       1 anchor + 1 partner  = 1 basis function  ✓
!    T-junction  (N=3):       1 anchor + 2 partners = 2 basis functions ✓
!    5-arm hub   (N=5):       1 anchor + 4 partners = 4 basis functions ✓
!      (e.g. disk-cone top-hat: 4 radial arms + 1 feed wire at hub)
!
!  Mathematical note:
!   The anchor choice is arbitrary — any segment can be the anchor.  The
!   resulting N-1 basis functions span the same current space regardless.
!   For best Z-matrix conditioning, similar-length anchor+partner segments
!   are preferable; the current implementation picks the first iEnd==2
!   segment found, which is adequate for typical meshes.
!
!==============================================================================
!  FUTURE WORK: half-rooftop at z=0 for monopole ground connection
!==============================================================================
!
!  Current behaviour: a node at z=0 with nTouch==1 is classified isWireEnd
!  and receives no basis function.  This forces J=0 at the monopole base,
!  giving wrong input impedance.
!
!  Fix: detect isWireEnd nodes at z=0 when a ground plane is present.
!  Build a BASIS2_TYPE using only half(1) (the above-ground segment) and
!  a synthetic half(2) whose iSeg points to a dummy image segment (or
!  use a flag in BASIS2_TYPE to mark single-half bases).  The image-theory
!  machinery already in zfill_m.f90 will handle the z<0 mirror automatically.
!  Changes confined to basis_builder_m.f90 (here) and excitation_m.f90.
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m, only: NODE_TYPE, SEGMENT_TYPE
   use connectivity_m

   implicit none; private

   public :: HALF_TYPE, BASIS2_TYPE, build_basis, seg_touch_to_half, write_basis2


!------------------------------------------------------------------------------
!  HALF_TYPE: one half of a rooftop basis function.
!
!  iSeg    -- segment index into Segs(:)
!  iEnd    -- 1=iLeftNode is hub, 2=iRightNode is hub  (from connectivity_m)
!  effSign -- ±1.0; chosen so half(1) has positive div, half(2) has negative
!  div     -- = effSign * naturalSign / Length  [1/m]
!             always +1/L for half(1), -1/L for half(2)
!
!  The vector current shape on the segment is:
!    J(x) = effSign * scalar(x, iEnd) * Segs(iSeg)%uHat * I_m
!  where I_m is the unknown current coefficient for the parent basis function.
!------------------------------------------------------------------------------
   type :: HALF_TYPE
      integer :: iSeg    = 0      ! segment index (0 = unset)
      integer :: iEnd    = 0      ! 1 = left-node hub, 2 = right-node hub
      real    :: effSign = ONE    ! +1.0 or -1.0 (see module header)
      real    :: div     = ZERO   ! signed divergence coefficient [1/m]
   end type HALF_TYPE


!------------------------------------------------------------------------------
!  BASIS2_TYPE: a complete rooftop basis function (two-half rooftop).
!
!  iNode    -- global index of the shared (peak) node
!  vNode(3) -- 3-D coordinates of the shared node [m]; stored for convenience
!              in pattern and Z-fill loops
!  half(2)  -- the two half-rooftop segments:
!                half(1): positive divergence (+div > 0)  "source side"
!                half(2): negative divergence (-div < 0)  "sink side"
!  radius   -- mean wire radius = (radius_half1 + radius_half2) / 2  [m]
!              used in self-term and near-field quadrature in zfill_m.f90
!------------------------------------------------------------------------------
   type :: BASIS2_TYPE
      integer         :: iNode    = 0       ! hub node index
      real            :: vNode(3) = ZERO    ! hub node coordinates [m]
      type(HALF_TYPE) :: half(2)            ! half(1): +div,  half(2): -div
      real            :: radius   = ZERO    ! mean wire radius [m]
   end type BASIS2_TYPE


contains

!==============================================================================
!  write_basis2: formatted debug dump of the Basis2(:) array.
!
!  Purpose:
!   Human-readable diagnostic output for verifying rooftop sign conventions,
!   junction wiring, and basis-function geometry.  Useful when debugging
!   impedance errors or unexpected pattern asymmetry.
!
!  Output file format (per basis function):
!   Header line: m, iNode, vNode (hub coords), mean radius
!   For each half h=1,2:
!     iSeg, wireTag, iEnd, naturalSign, effSign, stored div, recomputed div, L
!     uHat (segment unit vector, left→right)
!     vCtr (segment centroid)
!
!  Key invariants to verify:
!   half(1): div > 0   (positive divergence, source side)
!   half(2): div < 0   (negative divergence, sink side)
!   div == chk         (stored value matches re-derived effSign*nat/L)
!
!  Uses hardcoded unit=55; will silently skip if the file cannot be opened.
!==============================================================================
   subroutine write_basis2(Basis2, Segs, filename)

      type(BASIS2_TYPE),  intent(in) :: Basis2(:)
      type(SEGMENT_TYPE), intent(in) :: Segs(:)
      character(*),       intent(in) :: filename

      integer :: iU, m, h, iSeg, ios, nB
      real    :: natSign, divCheck, L

      iU = 55
      nB = size(Basis2)

      open(unit=iU, file=trim(filename), status='replace', &
           action='write', iostat=ios)
      if (ios /= 0) then
         write(*,'(a,a)') '  write_basis2: cannot open ', trim(filename)
         return
      end if

      write(iU,'(a)')    '=================================================================='
      write(iU,'(a,i6)') '  BASIS2 OUTPUT    nBasis =', nB
      write(iU,'(a)')    '=================================================================='
      write(iU,'(a)')    ''
      write(iU,'(a)')    '  iEnd : 1=iLeftNode is hub   2=iRightNode is hub'
      write(iU,'(a)')    '  nat  : naturalSign = 2*iEnd-3   (+1 or -1)'
      write(iU,'(a)')    '  eff  : effSign                  (+1 or -1)'
      write(iU,'(a)')    '  div  : stored effSign*nat/L     (h=1 >0, h=2 <0)'
      write(iU,'(a)')    '  chk  : recomputed from iSeg     (should match div)'
      write(iU,'(a)')    ''

      do m = 1, nB

         write(iU,'(a)')    '------------------------------------------------------------------'
         write(iU,'(a,i5,a,i6,a,3e12.4,a,a, g13.5)') &
            '  m=', m, &
            '  iNode=', Basis2(m)%iNode, &
            '  vNode=(', Basis2(m)%vNode, ')', &
            '  r=' , Basis2(m)%radius

         do h = 1, 2

            iSeg     = Basis2(m)%half(h)%iSeg
            L        = Segs(iSeg)%length
            natSign  = real(2*Basis2(m)%half(h)%iEnd - 3)   ! iEnd=1→-1, iEnd=2→+1
            divCheck = Basis2(m)%half(h)%effSign * natSign / L

            ! Line 1: indices and sign quantities
            write(iU,'(a,i1,a,i5,2x,a16,a,i1,a,f4.0,a,f4.0,a,f9.4,a,f9.4,a,f8.4)') &
               '    h=', h, &
               '  iSeg=', iSeg, &
               Segs(iSeg)%wireTag, &
               '  iEnd=', Basis2(m)%half(h)%iEnd, &
               '  nat=',  natSign, &
               '  eff=',  Basis2(m)%half(h)%effSign, &
               '  div=',  Basis2(m)%half(h)%div, &
               '  chk=',  divCheck, &
               '  L=',    L

            ! Line 2: geometry vectors
            write(iU,'(a,3f9.4,a,3f9.4,a)') &
               '           uHat=(', Segs(iSeg)%uHat, &
               ')   vCtr=(', Segs(iSeg)%vCtr, ')'

         end do ! h

      end do ! m

      write(iU,'(a)')    '=================================================================='
      write(iU,'(a,i6)') '  Total basis functions :', nB
      write(iU,'(a,i6)') '  Total segments        :', size(Segs)
      write(iU,'(a)')    '=================================================================='

      close(iU)
      write(*,'(a,a)') '  write_basis2: written to ', trim(filename)

   end subroutine write_basis2


!==============================================================================
!  build_basis: top-level entry point — build the complete Basis(:) array.
!
!  Input:
!   Segs(:)  -- mesh segments (post merge_nodes + seg_parameters)
!   Nodes(:) -- unique node array
!   Conn(:)  -- node connectivity table from build_connectivity
!
!  Output:
!   Basis(:) -- allocated array of BASIS2_TYPE, one entry per current DOF.
!               Total count = sum over non-tip nodes of (nTouch - 1).
!               For a simple wire: nBasis = nSegs - 1.
!               For a T-junction adding one branch of k segs: +k extra bases.
!
!  Algorithm:
!   Allocate a conservative tmp array (nSegs + nNodes entries is always
!   sufficient since at most nSegs - 1 bases arise from any connected mesh
!   plus at most nNodes/2 junction extras).  Walk every non-tip node and
!   call basis_at_node to populate tmp.  Trim to exact size at end.
!==============================================================================
   subroutine build_basis(Segs, Nodes, Conn, Basis)

      type(SEGMENT_TYPE),   intent(in)               :: Segs(:)
      type(NODE_TYPE),      intent(in)               :: Nodes(:)
      type(NODE_CONN_TYPE), intent(in)               :: Conn(size(Nodes))
      type(BASIS2_TYPE),    allocatable, intent(out) :: Basis(:)

      type(BASIS2_TYPE), allocatable :: tmp(:)
      integer :: iNode, nBasis, nSegs, nNodes

      nSegs  = size(Segs)
      nNodes = size(Nodes)

      ! Conservative upper bound: nSegs + nNodes is always sufficient
      allocate(tmp(nSegs + nNodes))
      nBasis = 0

      do iNode = 1, nNodes
         if (Conn(iNode)%isWireEnd)      cycle   ! no basis at open wire tips
         if (Conn(iNode)%nTouch < 2)     cycle   ! isolated node (shouldn't occur)
         call basis_at_node(iNode, Segs, Nodes(iNode), Conn(iNode), tmp, nBasis)
      end do

      allocate(Basis(nBasis))
      Basis = tmp(1:nBasis)

      write(*,'(a,i6,a,i6,a)') &
         '  build_basis: ', nBasis, ' basis functions from ', nSegs, ' segments'

   end subroutine build_basis


!==============================================================================
!  basis_at_node: generate the N-1 basis functions for one node.
!
!  Implements the "anchor + partners" junction strategy (see module header).
!
!  Anchor selection:
!   Scan C%touch(1..nTouch) for the first entry with iEnd==2.
!   iEnd==2 means the node is the right endpoint of that segment, so
!   naturalSign=+1 and effSign=+1 (no flip needed to get positive div).
!   If no iEnd==2 exists (all segments leave this node), use touch(1)
!   and effSign=-1 will flip its negative natural sign to positive.
!
!  For each partner (all touches except the anchor):
!   seg_touch_to_half(..., wantPositive=.false.) assigns effSign = -naturalSign,
!   giving div = -1/L < 0 regardless of the partner's storage direction.
!
!  radius stored as the arithmetic mean of the anchor and partner segment radii.
!  For a uniform-wire antenna this is just the wire radius; for mixed-radius
!  junctions (e.g. feed coax inner → dipole arm) it gives a reasonable average.
!==============================================================================
   subroutine basis_at_node(iNode, Segs, Node, C, tmp, nBasis)

      integer,              intent(in)    :: iNode
      type(SEGMENT_TYPE),   intent(in)    :: Segs(:)
      type(NODE_TYPE),      intent(in)    :: Node
      type(NODE_CONN_TYPE), intent(in)    :: C
      type(BASIS2_TYPE),    intent(inout) :: tmp(:)
      integer,              intent(inout) :: nBasis

      type(HALF_TYPE) :: anchorHalf, partnerHalf
      integer         :: anchorIdx, iT

      ! Select anchor: prefer iEnd==2 (natural positive div → effSign=+1)
      anchorIdx = 0
      do iT = 1, C%nTouch
         if (C%touch(iT)%iEnd == 2) then
            anchorIdx = iT
            exit
         end if
      end do
      if (anchorIdx == 0) anchorIdx = 1   ! all iEnd==1: first touch; effSign=-1 will flip

      anchorHalf = seg_touch_to_half(C%touch(anchorIdx), Segs, wantPositive=.true.)

      ! Pair anchor with each remaining segment (N-1 basis functions total)
      do iT = 1, C%nTouch
         if (iT == anchorIdx) cycle

         partnerHalf = seg_touch_to_half(C%touch(iT), Segs, wantPositive=.false.)

         nBasis = nBasis + 1
         if (nBasis > size(tmp)) &
            call FatalError('basis_builder_m: tmp array too small', '', 0)

         tmp(nBasis)%iNode   = iNode
         tmp(nBasis)%vNode   = Node%v
         tmp(nBasis)%half(1) = anchorHalf
         tmp(nBasis)%half(2) = partnerHalf
         tmp(nBasis)%radius  = 0.5 * ( Segs(anchorHalf%iSeg)%radius &
                                      + Segs(partnerHalf%iSeg)%radius )
      end do

   end subroutine basis_at_node


!==============================================================================
!  seg_touch_to_half: convert a SEG_TOUCH_TYPE to a HALF_TYPE.
!
!  naturalSign formula:
!   naturalSign = 2*touch%iEnd - 3
!     iEnd=1  →  2*1-3 = -1  (descending shape, negative div)
!     iEnd=2  →  2*2-3 = +1  (ascending shape,  positive div)
!
!  effSign assignment:
!   wantPositive=.true.  →  effSign =  naturalSign
!     → div = naturalSign²/L = +1/L  (positive regardless of iEnd)
!   wantPositive=.false. →  effSign = -naturalSign
!     → div = -naturalSign²/L = -1/L  (negative regardless of iEnd)
!
!  So |div| = 1/L always; only the sign is determined by wantPositive.
!  Note: Segs(iSeg)%div = 1/L is precomputed in seg_parameters but is NOT
!  used here; the length is fetched directly from Segs(iSeg)%length.
!
!  pure function: no side effects, callable from any context.
!==============================================================================
   pure function seg_touch_to_half(touch, Segs, wantPositive) result(H)

      type(SEG_TOUCH_TYPE), intent(in) :: touch
      type(SEGMENT_TYPE),   intent(in) :: Segs(:)
      logical,              intent(in) :: wantPositive
      type(HALF_TYPE)                  :: H

      real :: naturalSign, L

      H%iSeg = touch%iSeg
      H%iEnd = touch%iEnd

      naturalSign = real(2*touch%iEnd - 3)   ! iEnd=1 → -1,  iEnd=2 → +1

      if (wantPositive) then
         H%effSign = naturalSign    ! div > 0: keep natural sign
      else
         H%effSign = -naturalSign   ! div < 0: flip natural sign
      end if

      L     = Segs(touch%iSeg)%length
      H%div = H%effSign * naturalSign / L   ! = ±1/L  [1/m]

   end function seg_touch_to_half

end module basis_builder_m
