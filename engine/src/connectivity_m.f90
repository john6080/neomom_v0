module connectivity_m

!==============================================================================
!  connectivity_m
!
!  Purpose:
!   Build a node-to-segment adjacency table from the segment array.
!   This table is the sole input to basis_builder_m; it encodes everything
!   the basis builder needs to know about which segments meet at each node
!   and in what orientation.
!
!  Called once after mesh assembly:
!   merge_nodes → seg_parameters_from_iLeft_iRight_nodes → build_connectivity
!   The resulting Conn(:) array is then passed to build_basis.
!
!  iEnd orientation convention
!  ----------------------------
!  Every segment has a "left" node (iLeftNode) and a "right" node (iRightNode).
!  uHat always points left → right.  For each touch we record:
!
!    iEnd = 1  →  this node is iLeftNode  →  uHat points AWAY from node
!                 scalar basis shape: f ~ (L-x)/L   (descends from 1 at node to 0)
!                 natural divergence:  d/dx[(L-x)/L] = -1/L  (NEGATIVE)
!
!    iEnd = 2  →  this node is iRightNode  →  uHat points TOWARD node
!                 scalar basis shape: f ~  x/L       (ascends from 0 to 1 at node)
!                 natural divergence:  d/dx[x/L]    = +1/L  (POSITIVE)
!
!  This is the only orientation information basis_builder_m needs to assign
!  the correct ±1 effSign to each rooftop half via seg_touch_to_half().
!
!  Node classification by nTouch (number of touching segments):
!   nTouch == 1  →  isWireEnd  : open wire tip, no basis function centred here
!   nTouch == 2  →  isSimple   : standard interior node, one rooftop basis
!   nTouch >= 3  →  isJunction : T/Y/hub junction, nTouch-1 basis functions
!                                (KCL at the junction removes one DOF)
!
!  Example: disk-cone top-hat hub (4 radial arms + 1 feed wire)
!   nTouch = 5  →  isJunction  →  4 basis functions at that node  ✓
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m, only: SEGMENT_TYPE

   implicit none; private

   public :: SEG_TOUCH_TYPE, NODE_CONN_TYPE, build_connectivity

   !  MAX_TOUCH: maximum segments allowed at one node.
   !  24 handles any realistic mesh (a 12-arm radial hub uses 12).
   !  Increase this constant if build_connectivity calls FatalError for
   !  a dense junction.
   integer, parameter, public :: MAX_TOUCH = 24


!------------------------------------------------------------------------------
!  SEG_TOUCH_TYPE: one segment touching one node.
!
!  iSeg  -- index into the global Segs(:) array
!  iEnd  -- orientation of this node relative to the segment:
!             1 = this node is iLeftNode  (uHat leaves this node)
!             2 = this node is iRightNode (uHat arrives at this node)
!
!  The (iSeg, iEnd) pair fully specifies a rooftop half; seg_touch_to_half()
!  converts it to a HALF_TYPE with the correct effSign and div.
!------------------------------------------------------------------------------
   type :: SEG_TOUCH_TYPE
      integer :: iSeg = 0   ! segment index (0 = unset sentinel)
      integer :: iEnd = 0   ! 1 = left-node end,  2 = right-node end
   end type SEG_TOUCH_TYPE


!------------------------------------------------------------------------------
!  NODE_CONN_TYPE: complete adjacency record for one node.
!
!  nTouch      -- count of segments touching this node (valid entries in touch)
!  touch(1:nTouch) -- the touching segment records
!  isWireEnd   -- nTouch==1: open tip, basis_at_node skips this node
!  isSimple    -- nTouch==2: one standard rooftop basis function
!  isJunction  -- nTouch>=3: nTouch-1 basis functions (anchor + partners)
!
!  Fixed-size touch(MAX_TOUCH) array avoids dynamic allocation overhead.
!  Default initialisation (nTouch=0, flags=.false.) is set by intent(out)
!  in build_connectivity — no explicit zeroing needed.
!------------------------------------------------------------------------------
   type :: NODE_CONN_TYPE
      integer              :: nTouch    = 0
      type(SEG_TOUCH_TYPE) :: touch(MAX_TOUCH)
      logical :: isWireEnd  = .false.   ! open wire tip:      nTouch == 1
      logical :: isSimple   = .false.   ! interior node:      nTouch == 2
      logical :: isJunction = .false.   ! multi-seg junction: nTouch >= 3
   end type NODE_CONN_TYPE


contains

!==============================================================================
!  build_connectivity: populate Conn(:) from the segment array.
!
!  Input:
!   Segs(:)  -- complete mesh segments; iLeftNode and iRightNode must be
!               unique-node indices (post merge_nodes + remap)
!   nNodes   -- total unique nodes; caller allocates Conn(nNodes)
!
!  Output:
!   Conn(nNodes) -- filled adjacency table, one NODE_CONN_TYPE per node
!
!  Algorithm:
!   Pass 1 — register each segment with its left node (iEnd=1) and right
!             node (iEnd=2).  Bounds-checked; FatalError if out-of-range
!             or MAX_TOUCH exceeded.
!   Pass 2 — set the three classification flags from nTouch.
!
!  Note: intent(out) on Conn triggers default initialisation of all fields
!  (nTouch=0, isWireEnd=.false., etc.) before the loop, so no explicit
!  zeroing is needed.
!==============================================================================
   subroutine build_connectivity(Segs, nNodes, Conn)

      type(SEGMENT_TYPE),   intent(in)  :: Segs(:)
      integer,              intent(in)  :: nNodes
      type(NODE_CONN_TYPE), intent(out) :: Conn(nNodes)   ! caller-allocated

      integer :: iSeg, iNode, n

      ! Pass 1: walk every segment, register with its two endpoint nodes
      do iSeg = 1, size(Segs)

         !--- left node: uHat points AWAY → iEnd=1 ---
         iNode = Segs(iSeg)%iLeftNode
         if (iNode < 1 .or. iNode > nNodes) &
            call FatalError('connectivity_m: iLeftNode out of range', '', iSeg)

         n = Conn(iNode)%nTouch + 1
         if (n > MAX_TOUCH) &
            call FatalError('connectivity_m: MAX_TOUCH exceeded at node', '', iNode)

         Conn(iNode)%touch(n) = SEG_TOUCH_TYPE(iSeg, 1)   ! iEnd=1
         Conn(iNode)%nTouch   = n

         !--- right node: uHat points TOWARD → iEnd=2 ---
         iNode = Segs(iSeg)%iRightNode
         if (iNode < 1 .or. iNode > nNodes) &
            call FatalError('connectivity_m: iRightNode out of range', '', iSeg)

         n = Conn(iNode)%nTouch + 1
         if (n > MAX_TOUCH) &
            call FatalError('connectivity_m: MAX_TOUCH exceeded at node', '', iNode)

         Conn(iNode)%touch(n) = SEG_TOUCH_TYPE(iSeg, 2)   ! iEnd=2
         Conn(iNode)%nTouch   = n

      end do

      ! Pass 2: classify each node
      do iNode = 1, nNodes
         associate(C => Conn(iNode))
            C%isWireEnd  = (C%nTouch == 1)   ! open tip:        no basis function
            C%isSimple   = (C%nTouch == 2)   ! two-seg node:    one basis function
            C%isJunction = (C%nTouch >= 3)   ! multi-seg node:  nTouch-1 bases
         end associate
      end do

   end subroutine build_connectivity

end module connectivity_m
