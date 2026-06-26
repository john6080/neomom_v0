module nodes_wires_segments_m

!==============================================================================
!  nodes_wires_segments_m
!
!  Purpose:
!   Defines the three-tier geometry hierarchy used by the NeoMoM wire MOM
!   solver, and provides the routines that build and mesh that hierarchy.
!
!  Three-tier geometry pipeline:
!
!   Tier 1 -- Node primitives (NODE_TYPE):
!     User-supplied named control points (tags 'A','B','C',...) read from
!     the &node_input namelist.  After reading, a global zHeight offset and
!     unit conversion are applied so all coordinates are in metres.
!
!   Tier 2 -- Wire primitives (WIRE_PRIMITIVE_TYPE):
!     User-supplied polyline descriptors, each referencing an ordered list
!     of node-primitive tags.  Read from successive &wire_primitive namelists.
!     Each wire carries a radius (metres) and a desired segment length hint.
!
!   Tier 3 -- Segments (SEGMENT_TYPE):
!     The actual MOM mesh.  wireprimitive_segment() walks every wire
!     primitive, subdivides each span [nodeTag(i) → nodeTag(i+1)] into an
!     EVEN number of uniform segments, and stores them in the wire primitive.
!     merge_nodes() then collapses coincident endpoints (wire junctions) into
!     a unique global node set.  seg_parameters_from_iLeft_iRight_nodes()
!     fills the derived geometric properties (length, centre, uHat, div).
!
!  Calling sequence (from the top-level driver):
!   1. read_geometry_input   -- populate node_primitives and wire_primitives
!   2. wireprimitive_segment -- mesh wire primitives → segment arrays
!   3. merge_nodes           -- produce unique node array; return map(:)
!   4. remap seg%iLeftNode / seg%iRightNode using map(:)  [in connectivity_m]
!   5. seg_parameters_from_iLeft_iRight_nodes  -- fill length, uHat, div, ...
!
!  Namelist input format (both in the same .nml file):
!
!   &node_input
!     nNodes = 3,  units = 'm',  zHeight = 5.0,
!     node_list(1)%tag='A', node_list(1)%v = 0.0,0.0,0.0,
!     node_list(2)%tag='B', node_list(2)%v = 5.0,0.0,0.0,
!     node_list(3)%tag='C', node_list(3)%v = 5.0,0.0,5.0 /
!
!   &wire_primitive tag='w1', nNodes=2, nodeTags='A','B',
!                   radius=0.001, segLenHint=0.5 /
!   &wire_primitive tag='w2', nNodes=2, nodeTags='B','C',
!                   radius=0.001, segLenHint=0.5 /
!
!  Notes:
!   - read_wire_primitives reads until IOSTAT /= 0 (EOF or missing block);
!     place &wire_primitive namelists after &node_input in the file.
!   - zHeight is a global z-offset applied to ALL nodes after unit conversion.
!     It is the primary way to position an antenna at height h above ground.
!   - Commented-out types (BASIS_TYPEx, EXCITATION_TYPE) are historical;
!     their replacements live in basis_builder_m.f90 and excitation_m.f90.
!==============================================================================

   use basic_header_m
   use vector_and_utility_m

   implicit none; private

   public :: NODE_TYPE, SEGMENT_TYPE, WIRE_PRIMITIVE_TYPE, wireprimitive_segment &
             , read_geometry_input, merge_nodes


!------------------------------------------------------------------------------
!  NODE_TYPE: a named point in 3-D space.
!
!  tag  -- user label (typically a capital letter: 'A', 'B', 'C', ...).
!          Case-insensitive: vNodeTagged() normalises to upper case before
!          comparing.
!  v(3) -- Cartesian coordinates [x, y, z] in metres (after unit conversion
!          and zHeight offset).
!  iD   -- integer index, assigned sequentially; -99999 = unset sentinel.
!
!  Sentinels: v(3) = huge(1.0) and iD = -99999 flag nodes that have not yet
!  been initialised, making data errors visibly obvious in debug output.
!------------------------------------------------------------------------------
   type :: NODE_TYPE
      character(len=8) :: tag = ''          ! name label, e.g. 'A'
      real             :: v(3) = huge(1.0)  ! xyz coords [m]; huge = unset sentinel
      integer          :: iD = -99999       ! global index; -99999 = unset
   end type NODE_TYPE


!------------------------------------------------------------------------------
!  SEGMENT_TYPE: one MOM wire segment in the final mesh.
!
!  iD                -- global sequential segment index (1-based across all wires).
!  iLeftNode,
!  iRightNode        -- indices into the UNIQUE node array produced by
!                       merge_nodes().  After wireprimitive_segment() these
!                       point into the pre-merge global node list; the calling
!                       code (connectivity_m.f90) remaps them using map(:).
!  vNodes(3, 2)      -- column 1 = left node coords, column 2 = right node coords.
!  uHat(3)           -- unit vector from left node to right node (positive current
!                       direction for the rooftop basis function on this segment).
!  vCtr(3)           -- segment midpoint = (vNodes(:,1) + vNodes(:,2)) / 2.
!  Length            -- |vNodes(:,2) - vNodes(:,1)|, in metres.
!  radius            -- wire radius [m], copied from the parent wire primitive.
!  div               -- 1.0 / Length.
!                       Role in EFIE: the divergence ∇·J of a rooftop basis
!                       function is ±1/L (constant ±1 over each half-segment
!                       divided by segment length).  Precomputed here for
!                       efficient use in the scalar-potential (charge) term of
!                       zfill_m.f90.
!  wireTag           -- tag string of the parent WIRE_PRIMITIVE_TYPE, for
!                       diagnostics and possible future use.
!
!  Sentinels: vNodes, uHat, vCtr, div are all huge(1.0) until
!  seg_parameters_from_iLeft_iRight_nodes() is called.
!------------------------------------------------------------------------------
   type SEGMENT_TYPE

      integer       :: iD = -huge(1)        ! global segment index; -huge = unset
      integer       :: iLeftNode            ! index of left endpoint in unique node array
      integer       :: iRightNode           ! index of right endpoint in unique node array
      real          ::                      &
         Length  = 0.0            &  ! segment length [m]
         , radius = 0.0           &  ! wire radius [m] (from parent wire primitive)
         , vNodes(3, 2) = huge(1.0) &  ! (3,2): col1=left coords, col2=right coords [m]
         , uHat(3)  = huge(1.0)   &  ! unit vector left→right; huge = unset sentinel
         , vCtr(3)  = huge(1.0)   &  ! segment midpoint [m]; huge = unset
         , div      = huge(1.0)      ! 1/Length; used in EFIE charge term
      character(len=16) :: wireTag = ''     ! parent wire primitive label, e.g. 'w1'

   contains
      procedure :: seg_parameters_from_iLeft_iRight_nodes
   end type SEGMENT_TYPE


!------------------------------------------------------------------------------
!  WIRE_PRIMITIVE_TYPE: a user-defined polyline wire before meshing.
!
!  tag       -- user label (e.g. 'w1', 'dipole_arm_left').
!  nNodes    -- number of node tags in the ordered nodeTags list.
!  nodeTags  -- ordered list of node-primitive tags defining the polyline.
!               Each consecutive pair [nodeTags(i), nodeTags(i+1)] is one span.
!               Spans are meshed independently by wireprimitive_segment().
!  radius    -- wire radius [m] for all segments on this primitive.
!  closed    -- .true. if the wire forms a closed loop (last tag == first tag,
!               or auto-detected by read_wire_primitives).
!  Segments  -- segment array populated by wireprimitive_segment().
!  nodes     -- node array populated by wireprimitive_segment() (pre-merge).
!------------------------------------------------------------------------------
   type :: WIRE_PRIMITIVE_TYPE
      character(len=16)              :: tag    = ''      ! wire label
      integer                        :: nNodes = 0       ! number of endpoint tags
      character(len=8), allocatable  :: nodeTags(:)      ! ordered endpoint tag list
      real                           :: radius = 0.001   ! wire radius [m]
      logical                        :: closed = .false. ! closed loop flag
      type(SEGMENT_TYPE), allocatable :: Segments(:)     ! mesh segments (set by wireprimitive_segment)
      type(NODE_TYPE),    allocatable :: nodes(:)        ! pre-merge node list
   end type

contains

!==============================================================================
!  merge_nodes: collapse coincident nodes into a unique set.
!
!  After wireprimitive_segment() runs, segment endpoint nodes from different
!  wire primitives that share the same physical location (wire junctions)
!  exist as separate node records.  This routine merges them so each
!  distinct 3-D point appears exactly once in nodes_out.
!
!  Input:
!   nodes_in  -- all pre-merge nodes (concatenated from all wire primitives)
!   tol       -- coincidence tolerance [m]: two nodes are merged if
!                norm2(v_i - v_j) < tol.
!
!  Output:
!   nodes_out -- unique node array (size m <= n); IDs reset to 1..m.
!   map(i)    -- index in nodes_out that nodes_in(i) maps to.
!
!  After merging, the calling code must remap every seg%iLeftNode and
!  seg%iRightNode from pre-merge IDs to unique IDs:
!    seg%iLeftNode  = map(seg%iLeftNode)
!    seg%iRightNode = map(seg%iRightNode)
!
!  Complexity: O(n*m) with n = total pre-merge nodes, m = unique nodes.
!  Acceptable since geometry arrays are small (tens to hundreds of nodes).
!==============================================================================
   subroutine merge_nodes(nodes_in, nodes_out, map, tol)

      type(NODE_TYPE), intent(in)               :: nodes_in(:)
      type(NODE_TYPE), allocatable, intent(out) :: nodes_out(:)
      integer,         allocatable, intent(out) :: map(:)
      real,            intent(in)               :: tol   ! coincidence tolerance [m]

      integer :: i, j, m, n
      logical :: found

      n = size(nodes_in)

      allocate (map(n))
      allocate (nodes_out(n))  ! over-allocate; trim at end

      m = 0   ! count of unique nodes found so far

      do i = 1, n
         found = .false.
         ! Search existing unique nodes for a match within tol
         do j = 1, m
            if (norm2(nodes_in(i)%v - nodes_out(j)%v) < tol) then
               map(i) = j          ! node i maps to existing unique node j
               found = .true.
               exit
            end if
         end do

         if (.not. found) then
            m = m + 1              ! new unique node
            nodes_out(m) = nodes_in(i)
            map(i) = m
         end if
      end do

      ! Renumber IDs sequentially 1..m in the unique array
      do i = 1, m
         nodes_out(i)%iD = i
      end do

      nodes_out = nodes_out(:m)  ! trim to actual unique count

   end subroutine merge_nodes


!==============================================================================
!  wireprimitive_segment: mesh all wire primitives into uniform segments.
!
!  For each wire primitive, each span [nodeTags(i) → nodeTags(i+1)] is
!  divided into an EVEN number of equal-length segments:
!
!    nSeg = max(1, nint(len / seglengthDesired))
!    nSeg = nSeg + 1; nSeg = nSeg - mod(nSeg, 2)   <-- force even
!
!  Why even?  Rooftop (triangle) basis functions are centred on inter-segment
!  nodes.  An even segment count per span guarantees that the span midpoint
!  falls on a segment boundary (basis function hub), which is needed for a
!  symmetric basis function placement and correct junction treatment.
!
!  Global IDs (kGlobalNode, kGlobalSeg) are assigned sequentially across ALL
!  wire primitives.  These pre-merge IDs are what seg%iLeftNode and
!  seg%iRightNode hold on exit; merge_nodes() produces the map to remap them
!  to unique-node IDs.
!
!  Output: wire_primitives(iPrim)%Segments and wire_primitives(iPrim)%nodes
!  are allocated and filled for every primitive.
!==============================================================================
   subroutine wireprimitive_segment(node_primitives, wire_primitives, seglengthDesired)

      type(NODE_TYPE), allocatable, intent(in)              :: node_Primitives(:)
      type(WIRE_PRIMITIVE_TYPE), allocatable, intent(inout) :: wire_primitives(:)
      real, intent(in)                                      :: seglengthDesired  ! desired seg length [m]

      type(SEGMENT_TYPE)              :: seg
      type(SEGMENT_TYPE), allocatable :: SegsThisPrim(:)
      type(NODE_TYPE)                 :: nodeStart, nodeEnd
      type(NODE_TYPE), allocatable    :: nodesThisPrim(:)

      real      :: vStart(3), vEnd(3), vLen(3), len, uHat(3), seglen
      integer   :: iPrim, iTag, nSeg, i, kGlobalNode, kGlobalSeg
      character :: nodeTag*8

      kGlobalNode = 0; kGlobalSeg = 0  ! global counters across all primitives

      do iPrim = 1, size(wire_primitives)

         if (allocated(SegsThisPrim)) deallocate (SegsThisPrim, nodesThisPrim)
         allocate (SegsThisPrim(0), nodesThisPrim(0))

         do iTag = 1, size(wire_primitives(iPrim)%nodeTags) - 1

            ! Locate the starting and ending node primitives by tag name
            nodeTag = wire_primitives(iPrim)%nodeTags(iTag)
            vStart  = vNodeTagged(node_primitives, nodeTag)

            kGlobalNode = kGlobalNode + 1
            nodeStart%iD = kGlobalNode
            nodeStart%v  = vStart
            call append_node(nodesThisPrim, nodeStart)

            nodeTag = wire_primitives(iPrim)%nodeTags(iTag + 1)
            vEnd = vNodeTagged(node_primitives, nodeTag)

            vLen = vEnd - vStart
            len  = norm2(vLen)
            uHat = vLen/len

            ! Determine segment count: nearest integer, then force even
            nSeg = max(1, nint(len/seglengthDesired))
            nSeg = nSeg + 1
            nSeg = nSeg - mod(nSeg, 2)   ! guarantee even number of segments

            seglen = len/real(nSeg)       ! uniform segment length for this span

            do i = 1, nSeg
               kGlobalSeg  = kGlobalSeg + 1
               kGlobalNode = kGlobalNode + 1
               seg%iD = kGlobalSeg

               nodeEnd%v  = nodeStart%v + seglen*uHat
               nodeEnd%iD = kGlobalNode

               seg%radius     = wire_primitives(iPrim)%radius
               seg%iLeftNode  = nodeStart%iD  ! pre-merge global node index
               seg%iRightNode = nodeEnd%iD
               seg%vNodes(:, 1) = nodeStart%v
               seg%vNodes(:, 2) = nodeEnd%v   ! = nodeStart%v + seglen*uHat

               call append_segment(SegsThisPrim, seg)
               call append_node(nodesThisPrim, nodeEnd)

               nodeStart = nodeEnd   ! advance: end of this segment = start of next
            end do

         end do ! iTag

         ! Attach the completed segment and node lists to the wire primitive
         wire_primitives(iPrim)%Segments = SegsThisPrim
         wire_primitives(iPrim)%nodes    = nodesThisPrim

      end do ! iPrim

   end subroutine wireprimitive_segment


!==============================================================================
!  vNodeTagged: look up a node primitive by its tag string.
!
!  Returns v(3) = coordinates of the node whose tag matches cTagIn.
!  Case-insensitive: both the query and stored tags are uppercased before
!  comparison.  FatalError if the tag is not found.
!
!  Returns huge(1.0) in all components on error (but FatalError stops first).
!==============================================================================
   function vNodeTagged(node_primitives, cTagIn) result(v)

      use vector_and_utility_m
      type(NODE_TYPE), intent(in) :: node_Primitives(:)
      character(*),   intent(in)  :: cTagIn

      real      :: v(3)
      integer   :: inode
      character :: cTag*8, cNodeTag*8

      cTag = cTagIn
      v = -huge(1.0)
      call toupper(cTag)    ! normalise query to upper case

      do inode = 1, size(node_primitives)
         cNodeTag = node_primitives(iNode)%tag
         call toUpper(cNodeTag)
         if (trim(cTag) == trim(cNodeTag)) then
            v = node_Primitives(inode)%v
            exit
         end if
      end do

      ! If the loop ran to completion without a match, inode > size → fatal
      if (inode .gt. size(node_primitives)) &
         call FatalError('wire primitive node tag not found: '//cTagIn, '', 0)

   end function vNodeTagged


!==============================================================================
!  read_geometry_input: top-level geometry reader.
!
!  Called once before the frequency loop.  Reads the .nml input file unit iU
!  and populates:
!   node_Primitives -- control points with tags, coordinates, and units applied
!   wire_primitives -- wire polyline descriptors (not yet meshed into segments)
!   zHeight         -- global z-offset [m] applied to all nodes
!
!  Note: the mesh (segments) is NOT built here.  It is built separately by
!  wireprimitive_segment() so it can be re-created at each frequency if the
!  desired segment length (lambda/10, lambda/20, ...) changes with frequency.
!==============================================================================
   subroutine read_geometry_input(iU, node_Primitives, wire_primitives, zHeight)

      integer, intent(in)  :: iU
      type(NODE_TYPE), allocatable, intent(out) :: node_Primitives(:)
      type(WIRE_PRIMITIVE_TYPE), allocatable, intent(out) :: wire_primitives(:)
      real, intent(out) :: zHeight   ! global z-offset applied to all nodes [m]

      call read_nodes(iU, node_Primitives, zHeight)
      call read_wire_primitives(iU, wire_primitives)

   end subroutine read_geometry_input


!==============================================================================
!  read_nodes: read the &node_input namelist.
!
!  Namelist variables:
!   nNodes    -- number of nodes to read (max 1000)
!   units     -- coordinate units string ('m','cm','mm','inches','feet','lambda')
!   zHeight   -- global z-offset added to every node's z-coordinate AFTER
!                unit conversion.  Use this to place the antenna at height h
!                above the ground plane without changing individual coordinates.
!   node_list -- array of NODE_TYPE with fields %tag and %v(3).
!
!  Processing:
!   1. Read namelist → node_list(1:nNodes)
!   2. Convert coordinates: v = v * unitsCv  (metres)
!   3. Apply zHeight:       v(3) = v(3) + zHeight  (also converted)
!
!  node_list is a fixed-size local scratch array; the module supports up to
!  1000 nodes.  The caller receives an allocatable array of exactly nNodes.
!==============================================================================
   subroutine read_nodes(iU, node_Primitives, zHeight)

      use units_m
      use vector_and_utility_m

      integer, intent(in)                                   :: iU
      type(NODE_TYPE), allocatable, intent(out)             :: node_Primitives(:)
      real, intent(out)                                     :: zHeight

      integer            :: ios, nNodes, i
      character(len=8)   :: units
      character(len=256) :: msg
      type(NODE_TYPE)    :: node_list(1000)    ! fixed scratch: up to 1000 nodes
      type(UNITS_TYPE)   :: unitsIn

      namelist /node_input/ nNodes, units, zHeight, node_list

      rewind (iu)
      zHeight = 0.0

      read (iu, nml=node_input, iostat=ios, iomsg=msg)
      call nml_error("node_input", ios, msg)

      allocate (node_Primitives(nNodes))
      node_Primitives(1:nNodes) = node_list(1:nNodes)

      call unitsIn%init(units)   ! set unitsCv from units string

      ! Convert user coordinates to metres, then apply global z-offset
      do i = 1, nNodes
         node_Primitives(i)%v = node_Primitives(i)%v * unitsIn%unitsCv
      end do

      zHeight = zHeight * unitsIn%unitsCv   ! convert the offset too

      do i = 1, nNodes
         node_Primitives(i)%v(3) = node_Primitives(i)%v(3) + zHeight
      end do

   end subroutine read_nodes


!==============================================================================
!  read_wire_primitives: read successive &wire_primitive namelists.
!
!  Namelist variables (all reset to defaults before each read):
!   tag        -- wire label (e.g. 'w1')
!   nNodes     -- number of node tags in this primitive
!   nodeTags   -- ordered list of node-primitive tags (max 100 entries)
!   radius     -- wire radius [m] (default 0.001 m = 1 mm)
!   closed     -- .true. if wire forms a closed loop; auto-set if
!                 nodeTags(1) == nodeTags(nNodes)
!   segLenHint -- desired segment length hint [m]; read but NOT stored in the
!                 type (tmp%segLenHint line is commented out).  The actual
!                 segment length is supplied to wireprimitive_segment() by
!                 the caller, typically as a fraction of the free-space lambda.
!
!  Reads until IOSTAT /= 0 (EOF or no more &wire_primitive blocks).
!  Primitives are accumulated into a growable list via append_primitive().
!==============================================================================
   subroutine read_wire_primitives(u, prim)

      integer, intent(in) :: u
      type(WIRE_PRIMITIVE_TYPE), allocatable, intent(out) :: prim(:)

      integer :: ios, count
      type(WIRE_PRIMITIVE_TYPE)              :: tmp
      type(WIRE_PRIMITIVE_TYPE), allocatable :: list(:)
      character(len=16) :: tag
      integer           :: nNodes
      character(len=8)  :: nodeTags(100)    ! up to 100 endpoint tags per wire
      real              :: radius
      logical           :: closed
      real              :: segLenHint        ! read but not stored (see note above)

      character(len=256) :: msg

      namelist /wire_primitive/ tag, nNodes, nodeTags, radius, closed, segLenHint

      allocate (list(0))
      count = 0

      do   ! read loop: terminates on EOF or missing &wire_primitive block
         ! Reset defaults before each read so previous values don't bleed through
         tag        = ''
         nNodes     = 0
         nodeTags   = ''
         radius     = 0.001
         closed     = .false.
         segLenHint = 0.0

         read (u, nml=wire_primitive, iostat=ios, iomsg=msg)
         if (ios /= 0) exit   ! EOF or read error → done

         ! Auto-detect closed loop: first and last tag identical
         if (nodeTags(1) == nodeTags(nNodes)) closed = .TRUE.

         tmp%tag    = tag
         tmp%nNodes = nNodes
         tmp%radius = radius
         tmp%closed = closed

         if (allocated(tmp%nodeTags)) deallocate (tmp%nodeTags)
         allocate (tmp%nodeTags(nNodes))
         tmp%nodeTags = nodeTags(1:nNodes)

         call append_primitive(list, tmp)
         count = count + 1
      end do

      allocate (prim(count))
      prim = list

   end subroutine read_wire_primitives


!==============================================================================
!  Growable-list helpers: append_node, append_segment, append_primitive.
!
!  Classic Fortran pattern: allocate(tmp, n+1), copy, move_alloc.
!  Each call is O(n), giving O(n^2) total build cost.  Acceptable here
!  because geometry arrays are small (tens to hundreds of elements).
!==============================================================================

   subroutine append_node(list, item)
      type(NODE_TYPE), allocatable, intent(inout) :: list(:)
      type(NODE_TYPE), intent(in) :: item
      type(NODE_TYPE), allocatable :: tmp(:)
      integer :: n
      n = size(list)
      allocate (tmp(n + 1))
      if (n > 0) tmp(1:n) = list
      tmp(n + 1) = item
      call move_alloc(tmp, list)
   end subroutine

   subroutine append_segment(list, item)
      type(SEGMENT_TYPE), allocatable, intent(inout) :: list(:)
      type(SEGMENT_TYPE), intent(in) :: item
      type(SEGMENT_TYPE), allocatable :: tmp(:)
      integer :: n
      n = size(list)
      allocate (tmp(n + 1))
      if (n > 0) tmp(1:n) = list
      tmp(n + 1) = item
      call move_alloc(tmp, list)
   end subroutine

   subroutine append_primitive(list, item)
      type(WIRE_PRIMITIVE_TYPE), allocatable, intent(inout) :: list(:)
      type(WIRE_PRIMITIVE_TYPE), intent(in) :: item
      type(WIRE_PRIMITIVE_TYPE), allocatable :: tmp(:)
      integer :: n
      n = size(list)
      allocate (tmp(n + 1))
      if (n > 0) tmp(1:n) = list
      tmp(n + 1) = item
      call move_alloc(tmp, list)
   end subroutine


!==============================================================================
!  seg_parameters_from_iLeft_iRight_nodes: compute segment geometry.
!
!  Called after merge_nodes() and the iLeftNode/iRightNode remapping.
!  Uses seg%iLeftNode and seg%iRightNode as indices into Nodes(:) to
!  compute and store:
!
!   seg%vNodes(:,1) = Nodes(iLeftNode)%v     -- left endpoint [m]
!   seg%vNodes(:,2) = Nodes(iRightNode)%v    -- right endpoint [m]
!   seg%Length      = |vNodes(:,2) - vNodes(:,1)|
!   seg%vCtr        = midpoint
!   seg%uHat        = unit vector left → right
!   seg%div         = 1.0 / seg%Length       -- for EFIE scalar-potential term
!
!  div = 1/L is used in zfill_m.f90 for the scalar potential (charge)
!  contribution to Z_mn:
!    Phi_mn ~ (div_m * div_n) * integral(Green's function)
!  where div for a rooftop half is ±1/L (constant charge density).
!
!  Note: the first assignment of vlen (line 432) is immediately overwritten
!  by line 433; the redundant line is harmless.
!==============================================================================
   subroutine seg_parameters_from_iLeft_iRight_nodes(seg, Nodes)

      class(SEGMENT_TYPE), intent(inout) :: seg
      type(NODE_TYPE),     intent(in)    :: Nodes(:)

      integer :: iLeftNode, iRightNode
      real    :: V(3, 2), vlen(3)

      iLeftNode  = seg%iLeftNode
      iRightNode = seg%iRightNode

      seg%vNodes(:, 1) = nodes(iLeftNode)%v
      seg%vNodes(:, 2) = nodes(iRightNode)%v

      V = seg%vNodes

      ! Note: first line below is immediately overwritten by the second
      !vlen = v(:, 2) - v(:, 1)             ! redundant -- overwritten next line
      vlen = seg%vNodes(:, 2) - seg%vNodes(:, 1)

      seg%length = norm2(vLen)
      seg%vCtr   = 0.5*(v(:, 1) + v(:, 2))
      seg%uHat   = vlen/seg%length
      seg%div    = 1.0/seg%length   ! ∇·J coefficient for EFIE charge term

   end subroutine seg_parameters_from_iLeft_iRight_nodes

end module nodes_wires_segments_m
