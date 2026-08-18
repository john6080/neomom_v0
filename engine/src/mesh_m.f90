Module mesh_m

!==============================================================================
!  mesh_m
!
!  Purpose:
!   Top-level "solver state" container (MESH_TYPE) and the routines that
!   drive the full NeoMoM wire MOM assembly and solve pipeline.
!
!  MESH_TYPE holds every array needed from geometry input through Z-matrix
!  fill and pattern computation.  It is the single object passed between
!  the top-level driver and the physics kernels.
!
!  Full assembly sequence (assemble_mesh):
!   1. wireprimitive_segment  -- mesh wire primitives into per-primitive segments
!   2. Concatenate            -- flatten per-primitive node/segment arrays
!   3. merge_nodes            -- collapse coincident nodes; remap segment IDs
!   4. build_rooftop_basis2   -- compute segment geometry, connectivity, basis
!   5. Excitation setup       -- find feed node and feed basis function ID
!
!  Solve sequence (called by top-level driver after assemble_mesh):
!   a. matrix_fill            -- fill complex Z-matrix via ZFILL_TYPE
!   b. (solve) Ax = b         -- external LAPACK call (not in this module)
!   c. pattern_jfs_v2         -- far-field radiation pattern
!
!  Active vs. legacy code:
!   matrix_fill:    calls zfill_m::ZFILL_TYPE%fill_matrix exclusively.
!                   Operator_Wire_Module and matrix_fill_v2_m have been removed.
!   pattern_jfs_v2: active.  The older pattern() subroutine (uses old BASIS_TYPE
!                   with curSegSign) is fully commented out below it.
!   build_rooftop_basis2: active.  The older build_rooftop_basis() (uses
!                   EdgeIDs_ThisNode adjacency matrix and old BASIS_TYPE) is
!                   fully commented out; retained as historical reference.
!
!  Compile-time dependency order (must be compiled before mesh_m):
!   basic_header_m, vector_and_utility_m, units_m
!   nodes_wires_segments_m, connectivity_m, basis_builder_m
!   excitation_m, angle_cut_m, fresnel_reflection_m
!   zfill_m   ← used inside matrix_fill; zfill_m.f90 must precede mesh_m.f90
!
!  Removed modules (legacy, no longer referenced):
!   Operator_Wire_Module  — superseded by zfill_m; was only used in the
!                           unreachable legacy block of matrix_fill.
!   matrix_fill_v2_m      — earlier thin wrapper; also unreachable.
!==============================================================================

   use basic_header_m
   use vector_and_utility_m
   use units_m
   use nodes_wires_segments_m
   use angle_cut_m
   use fresnel_reflection_m
   use basis_builder_m
   use excitation_m

   implicit none; private

   public MESH_TYPE

!------------------------------------------------------------------------------
!  MESH_TYPE: complete solver state for one antenna geometry at one frequency.
!
!  Geometry (post-assembly):
!   Nodes(:)          -- unique mesh nodes [m] (post merge_nodes)
!   Segs(:)           -- mesh segments with geometry (length, uHat, vCtr, div)
!   basis2(:)         -- rooftop basis functions (see basis_builder_m)
!   excitations(:)    -- voltage source(s); nExcitations=1 by default
!   Reflection_Coef   -- Fresnel ground plane reflection coefficients
!
!  Geometry input (kept after assembly for excitation node lookups):
!   node_Primitives(:)  -- user-supplied control points (from &node_input)
!   wire_primitives(:)  -- user-supplied wire descriptors (from &wire_primitive)
!
!  Scalar parameters:
!   nSegs             -- number of mesh segments (= size(Segs))
!   nBasis            -- number of basis functions (= size(basis2))
!   nExcitations      -- number of voltage sources (default 1)
!   seglengthDesired  -- target segment length [m]; set before assemble_mesh
!   zHeightAboveGround -- global z-offset [m] applied to all nodes;
!                         stored here but applied inside read_geometry_input
!   bOutputCurrents   -- if .TRUE., write segment currents to file after solve
!   size              -- diagonal of bounding box [m], computed in assemble_mesh;
!                        useful as a sanity check on geometry scale
!------------------------------------------------------------------------------
   type MESH_TYPE

      type(NODE_TYPE), allocatable :: Nodes(:)        ! unique mesh nodes
      type(SEGMENT_TYPE), allocatable :: Segs(:)         ! mesh segments
      type(BASIS2_TYPE), allocatable :: basis2(:)       ! rooftop basis functions
      type(EXCITATION_TYPE), allocatable :: excitations(:)  ! voltage source(s)

      type(Fresnel_Reflection_Coef_Type) :: Reflection_Coef ! ground plane coefficients

      integer :: nSegs = 0   ! segment count
      integer :: nBasis = 0   ! basis function count
      integer :: nExcitations = 1   ! source count (default 1)

      type(NODE_TYPE), allocatable :: node_Primitives(:)  ! input control points
      type(WIRE_PRIMITIVE_TYPE), allocatable :: wire_primitives(:)  ! input wire descriptors

      real    :: seglengthDesired = 0.0     ! target segment length [m]
      real    :: zHeightAboveGround = 0.0     ! global z-offset [m]
      logical :: bOutputCurrents = .FALSE. ! write currents flag
      real    :: size = 0.0     ! bounding-box diagonal [m]

      ! Input coordinate units — preserved for data_out geometry report
      character(len=16) :: cInputUnits = 'm'   ! units string from &node_input
      real              :: inputUnitsCv = 1.0    ! metres per input unit

   contains

      procedure :: assemble_mesh        ! full geometry → basis pipeline
      procedure :: build_rooftop_basis2 ! inner: seg_params → connectivity → basis
      procedure :: pattern_jfs_v2       ! far-field pattern (centroid, image theory)
      procedure :: matrix_fill          ! Z-matrix fill (calls zfill_m)

   end type MESH_TYPE

contains

!==============================================================================
!  matrix_fill: fill the complex impedance matrix Z.
!
!  Active path:
!   call zClaude%fill_matrix(mesh%Basis2, mesh%Segs, bk0, zBlk, zReflection_Coef(1))
!
!  Reflection coefficient:
!   zReflection_Coef = mesh%Reflection_Coef%FRC(0.0) evaluates the Fresnel
!   coefficients at elevation angle 0.0 (grazing incidence).  Element (1) is
!   the vertical-polarization coefficient Γ_v, passed to fill_matrix for the
!   image-theory term in the Z-matrix.
!   For PEC:  Γ_v = -1 (exact, angle-independent) → correct.
!   For real ground: Γ_v is angle-dependent; using a fixed grazing value is an
!   approximation.  Per-segment-pair angle evaluation would require changes to
!   zfill_m::Z_half_pair.
!
!  Legacy paths (all commented out, unreachable after the first RETURN):
!   matrix_fill_v2:  earlier thin-wrapper call
!   Manual loop:     unoptimised prototype using old BASIS_TYPE with curSegSign;
!                    documents the EFIE accumulation Z(m,n) += j*k*ETA0*(L-Phi/k²)
!==============================================================================
   subroutine matrix_fill(mesh, bk0, zBlk)

      use zfill_m
      use zfill_nec_m

      class(MESH_TYPE), intent(inout)   :: mesh
      real, intent(in)                  :: bk0           ! k = 2π/λ [1/m]
      complex, allocatable, intent(out) :: zBlk(:, :)    ! nBasis×nBasis Z matrix

      complex           :: zReflection_Coef(2)   ! (1)=vert, (2)=horiz Fresnel coeff
      type(ZFILL_TYPE)  :: zClaude
      
      type(NEC_ZFILL_TYPE) :: zNEC5

      ! Evaluate Fresnel coefficients at grazing angle for image-theory Z-fill
      zReflection_Coef = mesh%Reflection_Coef%FRC(0.0)

      write (*, *) ' ETA0 =', ETA0   ! sanity: should print ~376.730 Ω

      ! --- ACTIVE path: zfill_nec_m NEC_ZFILL_TYPE ---
      ! Near-pair quadrature order is chosen automatically by select_nQ
      ! (zfill_nec_m), a seg_seg_distance-based graduated ladder -- no
      ! manual threshold tuning needed here. nearKernel stays BARE;
      ! C3_radMult stays 0 (isNearTouching reduces to pure node-sharing).
      call zNEC5%fill_matrix_nec(mesh%Basis2, mesh%Segs, bk0, zBlk, zReflection_Coef(1))
      !call zClaude%fill_matrix(mesh%Basis2, mesh%Segs, bk0, zBlk, zReflection_Coef(1))

      return

      ! --- LEGACY (unreachable; Operator_Wire_Module and matrix_fill_v2_m removed) ---
      ! The prior manual loop used OPERATOR_WIRE_TYPE::Loperator_wire to compute
      ! the 2×2 (Lop, G) pair per segment pair, then assembled Z(m,n) as:
      !   Z(m,n) += j*k*ETA0 * (Lop(ivp,ivq) - G/k²)
      ! See Operator_Wire_v2_m.f90 for the full algorithmic reference.

   end subroutine matrix_fill

!==============================================================================
!  pattern_jfs_v2: far-field radiation pattern using centroid approximation.
!
!  Computes Er(nAng, 2) — the far-field electric field at nAng observation
!  directions, decomposed into two polarisations (vertical=1, horizontal=2).
!
!  Physics — contribution from one basis function iR, half p, at angle iAng:
!
!    vRad = uHat * L * cur(iR) * Favg * exp(+j*k̂·r_seg) / (4π)
!
!  where:
!    uHat    = effSign * (vLen / |vLen|)  — reconstructed from node coords
!    L       = Sq%length
!    Favg    = HALF (0.5) — average of the triangle shape function over [0,L]
!    r_seg   = Sq%vCtr    — centroid approximation for the phase factor
!    k̂      = -AngleCut%vk * bk  (propagation vector pointing toward observer)
!
!  Accumulated field:
!    Er(iAng,iPol) -= (j*k*ETA0) * [dot(uPol,vRad) + dot(uPol,vRad_image)*Γ_iPol]
!
!  uHat reconstruction (differs from old pattern() which used Sq%uHat*curSegSign):
!   iEnd=1 (hub=left):  vLen = vRight - vCtr  (vector from hub to far end)
!   iEnd=2 (hub=right): vLen = vCtr  - vLeft  (vector from far end to hub)
!   uHat = effSign * vLen/|vLen|
!   Result: uHat always aligned with physical current direction for this half.
!
!  Ground plane image theory:
!   vR(3) negated → image source below ground.
!   uHat_image(3) negated → image of vertical current reverses; horiz. unchanged.
!   Fresnel: per-polarisation Γ_iPol from FRC(elevation_angle_iAng).
!
!  Note: the older pattern() (fully commented out below) uses old BASIS_TYPE
!  and curSegSign; it is NOT compatible with basis2.
!==============================================================================
   subroutine pattern_jfs_v2(mesh, bk, AngleCut, cur, Er)

      class(MESH_TYPE), intent(inout)      :: mesh
      real, intent(in)                  :: bk
      type(ANGLE_CUT_TYPE), intent(in)  :: AngleCut
      complex, intent(in)               :: cur(:)        ! basis function currents

      complex, allocatable, intent(out) :: Er(:, :)      ! Er(nAng,2): v-pol and h-pol

      type(SEGMENT_TYPE) :: Sq
      integer      :: nAng
      real(wp)     :: vk(3), vR(3), arg_fs, arg_gp, uHat_image(3), uHat(3), effSign
      integer      :: iAng, iPol, iR, p, i
      complex(wp)  :: vRad(3), vRad_image(3)
      complex(wp)  :: G_free_space, G_ground_reflection, zReflection_Coef(2)
      real         :: vCtr(3), vLeft(3), vRight(3), vLen(3)
      integer      :: iNode_ctr, iNode_left, iNode_Right, iEnd

      associate (nodes => mesh%nodes)

         nAng = AngleCut%nAng
         allocate (Er(nAng, 2))
         Er = zZERO

         do iAng = 1, nAng
            do iR = 1, mesh%nBasis          ! sum over all basis functions
               do p = 1, 2                  ! p=1: +div half,  p=2: -div half

                  i = mesh%basis2(iR)%half(p)%iSeg
                  Sq = mesh%segs(i)

                  ! Retrieve hub and endpoint coordinates for uHat reconstruction
                  iNode_ctr = mesh%basis2(iR)%iNode
                  iNode_left = Sq%iLeftNode
                  iNode_Right = Sq%iRightNode
                  vCtr = nodes(iNode_ctr)%v
                  vLeft = nodes(iNode_Left)%v
                  vRight = nodes(iNode_Right)%v

                  iEnd = mesh%basis2(iR)%half(p)%iEnd
                  effSign = mesh%basis2(iR)%half(p)%effSign

                  ! Reconstruct current direction from node positions
                  select case (iEnd)
                  case (1)   ! descending: hub=left, current flows away from hub
                     vLen = vRight - vCtr
                  case (2)   ! ascending: hub=right, current flows toward hub
                     vLen = vCtr - vLeft
                  end select
                  uHat = effSign*(vLen/norm2(vLen))

                  ! Free-space phase: k̂ · r_seg  (centroid approximation)
                  vk = -AngleCut%vk(:, iAng)*bk
                  vR = Sq%vCtr
                  arg_fs = dot_product(vk, vR)
                  G_free_space = exp(+zIMAG*arg_fs)

                  ! Vector potential: uHat * L * I * Favg * G / (4π),  Favg=HALF
                  vRad(:) = uHat*Sq%length*cur(iR)*HALF*G_free_space/FOURPI

                  ! Ground plane image
                  vRad_Image(:) = zZERO
                  zReflection_Coef = zZERO

                  if (mesh%Reflection_Coef%cGround_Plane /= cFreeSpace) then
                     vR(3) = -vR(3)
                     arg_gp = dot_product(vk, vR)
                     G_ground_reflection = exp(+zIMAG*arg_gp)
                     zReflection_Coef = mesh%Reflection_Coef%FRC(AngleCut%thr(iAng))

                     uHat_Image = uHat
                     uHat_Image(3) = -uHat_Image(3)   ! z-current reverses for image

                     vRad_image(:) = +uHat_Image*Sq%length*Cur(iR)*HALF &
                                     *G_ground_reflection/FOURPI
                  end if

                  ! Accumulate into polarisation components
                  do iPol = 1, 2
                     Er(iAng, iPol) = Er(iAng, iPol) - (zIMAG*bk*ETA0) &
                                      *(dot_product(AngleCut%uPol(:, iAng, iPol), vRad) &
                                        + dot_product(AngleCut%uPol(:, iAng, iPol), vRad_Image) &
                                        *zReflection_Coef(iPol))
                  end do

               end do ! p
            end do ! iR
         end do ! iAng

      end associate

   end subroutine pattern_jfs_v2

   ! Legacy pattern() — uses old BASIS_TYPE with curSegSign; not compatible
   ! with basis2.  See original mesh_m source for the full commented body.

!==============================================================================
!  first_token: extract first whitespace-delimited token from a string.
!  Private utility; used in input-file parsing.
!==============================================================================
   function first_token(line) result(tok)
      character(len=*), intent(in) :: line
      character(len=32) :: tok
      integer :: i
      i = index(line, ' ')
      if (i == 0) then
         tok = trim(line)
      else
         tok = trim(line(:i - 1))
      end if
   end function first_token

!==============================================================================
!  assemble_mesh: execute the full geometry assembly pipeline.
!
!  Must be called once per frequency (seglengthDesired changes with lambda):
!
!  Step 1 — wireprimitive_segment:
!   Meshes each wire primitive span into an even number of segments of
!   length ≈ seglengthDesired.  Results stored in each wire_primitive.
!
!  Step 2 — bounding box:
!   this%size = diagonal of the bounding box of node_Primitives coords [m].
!   Diagnostic; not used by the physics kernels.
!
!  Step 3 — flatten arrays:
!   Concatenates per-primitive node and segment arrays into flat arrays
!   nodesInitial(:) and SegsInitial(:).  Also copies wireTag from the parent
!   wire_primitive into each segment (uppercased via toUpper).
!
!  Step 4 — merge_nodes:
!   Collapses coincident nodes within tol = min(seglengthDesired, shortest
!   realized segment length) * 0.001 -- not seglengthDesired alone, which is
!   only the wavelength-relative target and can exceed the actual length of
!   a short, physically-fixed stub wire (e.g. a center-feed jumper) at low
!   frequency/coarse NBASISPERLAMBDA, merging away one of its nodes and
!   collapsing a segment to zero length.
!   Returns map(:): map(i_old) = j_new.  The iLeftNode and iRightNode of
!   every segment are immediately remapped using map.
!
!  Step 5 — build_rooftop_basis2:
!   Calls seg_parameters_from_iLeft_iRight_nodes, build_connectivity,
!   build_basis, and excitation setup.
!
!  Note: node_Primitives and wire_primitives are retained in the mesh after
!  assembly because excitation_m needs to look up feed nodes by tag name.
!==============================================================================
   subroutine assemble_mesh(this)

      class(MESH_TYPE), intent(inout) :: this

      integer :: nNodesInitial, nSegsInitial, i, is, ie

      type(NODE_TYPE), allocatable :: nodesInitial(:), nodes_Out(:)
      type(SEGMENT_TYPE), allocatable :: SegsInitial(:)
      integer, allocatable            :: map(:)

      integer, parameter :: iLeft = 1, iRight = 2
      real               :: tol, vSize_max(3), vSize_min(3), minSegLen, segLen
      logical            :: not_free_space = .true.
      !character          :: nodeTag*8, wireTag*16

      ! Step 1: mesh each wire primitive into segments
      call wireprimitive_segment(this%node_primitives, this%wire_primitives, this%seglengthDesired)

      ! Step 2: bounding box diagonal (diagnostic)
      vSize_max = -huge(1.); vSize_min = +huge(1.)

      do i = 1, size(this%node_Primitives)
         vSize_min = min(vSize_min, this%node_primitives(i)%v)
         vSize_max = max(vSize_max, this%node_primitives(i)%v)
      end do

      !Need Z image size for cases that are not free_space

      not_free_space = (this%Reflection_Coef%cGround_Plane /= cFreeSpace)

      if (not_free_space) then
         do i = 1, size(this%node_Primitives)
            vSize_min = min(vSize_min, -this%node_primitives(i)%v)
            vSize_max = max(vSize_max, -this%node_primitives(i)%v)
         end do
      end if

      this%size = norm2(vSize_max - vSize_min)

      ! Step 3: flatten per-primitive arrays
      nNodesInitial = 0; nSegsInitial = 0
      do i = 1, size(this%wire_primitives)
         nNodesInitial = nNodesInitial + size(this%wire_primitives(i)%nodes)
         nSegsInitial = nSegsInitial + size(this%wire_primitives(i)%segments)
      end do

      if (allocated(nodesInitial)) deallocate (nodesInitial, SegsInitial)
      allocate (nodesInitial(nNodesInitial), SegsInitial(nSegsInitial))

      is = 1
      do i = 1, size(this%wire_primitives)
         ie = is + size(this%wire_primitives(i)%nodes) - 1
         nodesInitial(is:ie) = this%wire_primitives(i)%nodes(:)
         is = ie + 1
      end do

      is = 1
      do i = 1, size(this%wire_primitives)
         ie = is + size(this%wire_primitives(i)%Segments) - 1
         SegsInitial(is:ie) = this%wire_primitives(i)%Segments(:)
         SegsInitial(is:ie)%wireTag = this%wire_primitives(i)%tag   ! stamp parent label
         is = ie + 1
      end do

      ! Step 4: merge coincident nodes; remap segment endpoint IDs
      ! tol = 0.1% of the shortest segment actually realized by
      ! wireprimitive_segment, not of seglengthDesired (the wavelength-
      ! relative target length) -- using seglengthDesired directly can bite
      ! short, physically-fixed stub wires (e.g. a center-feed jumper
      ! between two long antiparallel runs) at low frequency/coarse
      ! NBASISPERLAMBDA: seglengthDesired can grow well past the stub's own
      ! sub-segment length, merging one of its intermediate nodes into a
      ! neighboring node and collapsing that segment to zero length (which
      ! then divides by zero in the self-term impedance formula,
      ! zfill_nec_m_15.f90::source_self_rtwk). Using the true shortest
      ! realized segment keeps tol always far below any legitimate segment.
      minSegLen = huge(1.0)
      do i = 1, size(SegsInitial)
         segLen = norm2(SegsInitial(i)%vNodes(:, 2) - SegsInitial(i)%vNodes(:, 1))
         minSegLen = min(minSegLen, segLen)
      end do
      tol = min(this%seglengthDesired, minSegLen)*0.001

      call merge_nodes(nodesInitial, nodes_out, map, tol)
      this%Nodes = nodes_out

      do i = 1, size(SegsInitial)
         segsInitial(i)%iLeftNode = map(segsInitial(i)%iLeftNode)
         segsInitial(i)%iRightNode = map(segsInitial(i)%iRightNode)
         call toUpper(segsInitial(i)%wireTag)
      end do

      this%segs = SegsInitial
      this%nSegs = size(SegsInitial)

      ! Step 5: segment geometry, connectivity, basis functions, excitation
      call this%build_rooftop_basis2()

      associate (basis => this%basis2, nodes => this%Nodes, Segs => this%segs)
         !  Uncomment to dump basis function data for debugging:
         !  call write_basis2(Basis, Segs, 'basis2_data.txt')
      end associate

   end subroutine assemble_mesh

!==============================================================================
!  build_rooftop_basis2: inner assembly — segment geometry, connectivity,
!                         basis functions, and excitation setup.
!
!  Steps:
!   1. seg_parameters_from_iLeft_iRight_nodes: compute Length, uHat, vCtr, div
!   2. build_connectivity: build NODE_CONN_TYPE adjacency table (Conn local)
!   3. build_basis: generate BASIS2_TYPE array; print junction/count report
!   4. Store basis2 in mesh
!   5. Excitation loop: find_feed_node → find_basis_ID → print_excitation
!
!  Conn is local; the caller does not need it after this subroutine returns.
!==============================================================================
   subroutine build_rooftop_basis2(this)

      use basis_builder_m
      use connectivity_m

      class(MESH_TYPE), intent(inout) :: this

      type(NODE_CONN_TYPE), allocatable :: Conn(:)
      type(BASIS2_TYPE), allocatable :: Basis2(:)

      integer :: nSeg, nNodes, iSeg, iNode, i

      associate (segs => this%Segs, nodes => this%nodes)

         nSeg = size(segs)
         nNodes = size(nodes)

         ! Step 1: segment geometric properties from unique nodes
         do iSeg = 1, nSeg
            call segs(iSeg)%seg_parameters_from_iLeft_iRight_nodes(Nodes)
         end do

         ! Step 2: node-to-segment adjacency
         allocate (Conn(nNodes))
         call build_connectivity(Segs, nNodes, Conn)

         ! Step 3: rooftop basis functions
         call build_basis(Segs, Nodes, Conn, Basis2)

         ! Report junction nodes (for verifying complex multi-wire geometry)
         do iNode = 1, nNodes
            if (Conn(iNode)%isJunction) then
               write (*, '(a,i5,a,i3,a,i3,a)') '  Junction node ', iNode, &
                  ': ', Conn(iNode)%nTouch, ' segments, ', &
                  Conn(iNode)%nTouch - 1, ' basis functions'
            end if
         end do
         write (*, '(a,i6)') '  Total new basis count: ', size(Basis2)

         ! Step 4: store basis in mesh
         if (allocated(this%Basis2)) deallocate (this%Basis2)
         allocate (this%basis2(size(Basis2)))
         this%nBasis = size(Basis2)
         this%basis2 = Basis2

         ! Step 5: excitation setup
         ! find_feed_node: locate hub node by wire+node tag from &excitation namelist
         ! find_basis_ID:  find basis function m whose iNode == feed node
         ! print_excitation: print feed node, basis index, voltage to stdout
         associate (Excit => this%excitations, mesh => this)
            do i = 1, size(Excit)
               call Excit(i)%find_feed_node(mesh%wire_primitives, &
                                            mesh%node_primitives, &
                                            mesh%Nodes)
               call Excit(i)%find_basis_ID(mesh%Basis2, mesh%Segs, Conn)
               call Excit(i)%print_excitation()
            end do
         end associate

      end associate

   end subroutine build_rooftop_basis2

   ! Legacy build_rooftop_basis() — uses old EdgeIDs_ThisNode adjacency matrix
   ! and old BASIS_TYPE.  Fully superseded by build_rooftop_basis2.
   ! See original mesh_m source for the full commented body.

end Module mesh_m
