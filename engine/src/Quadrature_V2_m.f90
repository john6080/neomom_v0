Module quadrature_v2_m

!==============================================================================
!  quadrature_v2_m
!
!  Purpose:
!   Provides Gauss-Legendre quadrature for 1-D integrals (wire segments)
!   and Dunavant quadrature for 2-D triangle integrals (surface MOM, legacy).
!
!  NeoMoM wire MOM usage:
!   Only the 1-D Gauss-Legendre path is active:
!     call Quad_GAUSS_Init(gQ, 16, cNEAR)   -- 16-point rule on [0,1]
!   The resulting gQ%vXi(:,1) and gQ%w(:) are the integration points and
!   weights used in zfill_m.f90 for NEAR and MID-range segment-to-segment
!   interactions in the EFIE Z-matrix fill.
!
!  Legacy (surface MOM, not used in wire solver):
!   Quad_Triangle_Init / DQRULE -- Dunavant rules for triangle domains.
!   These are retained for compatibility; they are not called by the
!   wire-MOM kernel.
!
!  Quadrature type index constants (used in zfill_m.f90):
!   iFAR = 1 : far-field  (centroid approximation, single point)
!   iNEAR= 2 : near-field (16-point Gauss-Legendre)
!   iSELF= 3 : self-term  (analytical Gibson formula, no quadrature)
!   iCENTROID= 4 : centroid (single-point, triangle legacy)
!   iGAUSS   = 5 : Gauss (general, triangle legacy)
!
!  Precision note:
!   dp = real32 (single) for stored weights and points.
!   GAULEG internally uses real(8) (double) for Newton iteration accuracy,
!   then stores the converged roots at single precision.  This gives
!   full-precision Legendre roots stored at working precision.
!==============================================================================

   use basic_header_m
   use, intrinsic :: iso_fortran_env, only: int32, real32, real64, output_unit

   implicit none; private

   public  GENERAL_QUAD_TYPE, Quad_GAUSS_Init

   integer, parameter :: i4b = int32
   integer, parameter :: dp  = real32   ! quadrature storage precision

!  Quadrature type indices -- used as array selectors in zfill_m.f90
!  to choose the appropriate integration rule for each segment pair.
   integer(i4b), public, parameter ::  &
        iFAR      = 1   &  ! far:      centroid single-point approximation
      , iNEAR     = 2   &  ! near:     N-point Gauss-Legendre (N=16 in NeoMoM)
      , iSELF     = 3   &  ! self:     analytical Gibson self-term, no quadrature
      , iCENTROID = 4   &  ! centroid: single-point (triangle legacy)
      , iGAUSS    = 5      ! Gauss:    general (triangle legacy)

!  Character tags for quadrature quality -- passed to init routines
!  to label what each rule will be used for.
   character(4), public, parameter ::  &
        cTRI      = 'TRI'  &   ! triangle domain (Dunavant)
      , cTET      = 'TET'  &   ! tetrahedron domain (legacy, not implemented here)
      , cGAUSS    = 'GAUS' &   ! 1-D Gauss-Legendre
      , cNEAR     = 'NEAR' &   ! near-field wire interaction
      , cFAR      = 'FAR'  &   ! far-field wire interaction
      , cSELF     = 'SELF' &   ! self-term (no actual quadrature)
      , cCENTROID = 'CENTROID'  ! centroid rule

!------------------------------------------------------------------------------
!  GENERAL_QUAD_TYPE
!
!  A single container for either 1-D or 2-D quadrature rules.
!
!  For 1-D Gauss-Legendre (cType = cGAUSS):
!   vXi(nQ, 1)  -- integration abscissae on [0,1], stored in column 1
!   w(nQ)       -- corresponding weights (sum = 1 for [0,1])
!
!  For 2-D Dunavant triangle (cType = cTRI, legacy):
!   vXi(3, nQ)  -- area coordinates (L1, L2, L3) for each quadrature point
!   w(nQ)       -- weights (sum = 1 for unit triangle)
!
!  Note the transposed storage between the two cases: for GAUSS, the first
!  index is the point index; for TRI, the first index is the coordinate index.
!------------------------------------------------------------------------------
   type GENERAL_QUAD_TYPE
      integer(i4b)          :: nQ       = 0      ! number of quadrature points
      real(dp), allocatable :: vXi(:,:)          ! abscissae: (nQ,1) for GAUSS, (3,nQ) for TRI
      real(dp), allocatable :: w(:)              ! weights, size(nQ)
      character(4)          :: cType    = 'null' ! cGAUSS or cTRI
      character(4)          :: cQuality = 'null' ! cNEAR, cFAR, cSELF, cCENTROID, etc.
   contains
      procedure :: Quad_Triangle_Init
      procedure :: Quad_GAUSS_Init
      procedure, private :: dqrule
      procedure, private :: gauleg
   end type

contains

!==============================================================================
!  1-D Gauss-Legendre quadrature (active in NeoMoM)
!==============================================================================

!------------------------------------------------------------------------------
!  Quad_GAUSS_Init: allocate and fill an N-point Gauss-Legendre rule on [0,1].
!
!  nQ    : number of quadrature points (NeoMoM uses 16 for NEAR interactions)
!  cQual : quality tag (e.g., cNEAR) stored for caller reference
!
!  On return:
!   gQ%vXi(:,1) = abscissae x_i in (0,1)
!   gQ%w(:)     = weights w_i  with  sum(w_i) = 1
!
!  A 16-point rule integrates polynomials of degree up to 2*16-1 = 31 exactly.
!  For the EFIE wire integrand (1/R kernel with near-field variation), 16 points
!  gives adequate accuracy for segment separations >= ~0.3 * segment length.
!  Closer separations are handled by the analytical self-term (iSELF).
!------------------------------------------------------------------------------
   subroutine Quad_GAUSS_Init(gQ, nQ, cQual)
      class(GENERAL_QUAD_TYPE), intent(Out) :: gQ
      integer(i4b),             intent(in)  :: nQ
      character(*),             intent(in)  :: cQual

      gQ%nQ       = nQ
      gQ%cType    = cGAUSS
      gQ%cQuality = cQual

      allocate (gQ%vXi(gQ%nQ, 1), gQ%W(gQ%nQ))

      ! Compute Legendre roots and weights on [0,1] via Newton iteration
      call gq%gauleg(0.0_dp, 1.0_dp, gQ%vXi(:,1), gQ%w, gQ%nQ)

   end subroutine Quad_GAUSS_Init

!==============================================================================
!  2-D Dunavant triangle quadrature (legacy -- not used in wire MOM)
!==============================================================================

!------------------------------------------------------------------------------
!  Quad_Triangle_Init: allocate and fill a Dunavant quadrature rule for
!  numerical integration over a triangle in area coordinates.
!
!  Valid values of nQ (number of points):
!    1, 3, 4, 6, 7, 12, 13, 16, 19, 25, 27, 33, 37, 42, 48, 52, 61
!  Fatal error for any other value.
!
!  On return:
!   tQ%vXi(3, nQ) = area coordinate triplets (L1,L2,L3) for each point
!   tQ%w(nQ)      = weights
!
!  Reference: Dunavant, I.J.N.M.E., vol. 21, pp. 1129-1148, 1985.
!  This routine is retained for legacy surface-MOM compatibility and is
!  not called by the NeoMoM wire solver.
!------------------------------------------------------------------------------
   subroutine Quad_Triangle_Init(tQ, nQ, cQual)
      class(GENERAL_QUAD_TYPE), intent(Out) :: tQ
      integer(i4b),             intent(in)  :: nQ
      character(*),             intent(in)  :: cQual

      integer(i4b), parameter :: iDEG = 0, nCORD = 3  ! DQRULE: NQP control, area coords
      integer(i4b)            :: iErr
      character(80)           :: cLine

      tQ%nQ       = nQ
      tQ%cType    = cTRI
      tQ%cQuality = cQual

      if (allocated(tq%w)) deallocate (tq%w, tq%vXi)
      allocate (tq%vXi(3, nQ), tQ%w(nQ))

      call tq%dqrule(iDEG, tQ%nQ, nCORD, tQ%vXi, tQ%w, iErr)

      if (iErr /= 0) then
         write(cLine,*) 'Number of tri quadrature points invalid.  Valid values are: '
         call out(cLine)
         write(cLine,*) '1, 3, 4, 6, 7, 12, 13, 16, 19, 25, 27, 33, 37, 42, 48, 52, 61'
         call out(cLine)
         call fatalError('Quad_Triangle_Init Failed', 'iErr', iErr)
      endif

   end subroutine Quad_Triangle_Init

!==============================================================================
!  DQRULE -- Dunavant quadrature table lookup (private, triangle legacy)
!==============================================================================

!------------------------------------------------------------------------------
!  DQRULE: return Gauss quadrature points and weights for integration over
!  a triangle, using the Dunavant rules (degree 1 through 17).
!
!  Reference: Dunavant, D.A., "High degree efficient symmetrical Gaussian
!    quadrature rules for the triangle", Int. J. Numer. Methods Eng.,
!    vol. 21, pp. 1129-1148, 1985.
!
!  Input control (two modes):
!   IDEG=0, NQP=desired_points : use NQP control -- look up the rule with
!                                 that exact number of points.
!   IDEG=1..17, NQP=0          : use degree control -- return the rule
!                                 integrating polynomials up to degree IDEG.
!
!  Valid NQP values: 1,3,4,6,7,12,13,16,19,25,27,33,37,42,48,52,61
!  iErr = 0 on success, 1 on invalid IDEG or NQP.
!
!  The compact table stores one representative point per symmetry class.
!  KOUNTS(j) indicates the class multiplicity:
!    KOUNT = 1 : centroid (one point, no permutation needed)
!    KOUNT = 3 : two distinct area coords -- generates 3 permuted copies
!    KOUNT = 6 : three distinct area coords -- generates all 6 permutations
!  The expansion loop below inflates the compact table to the full NQP points.
!
!  Coordinates:
!   NCORD=3 : area coordinates (L1,L2,L3), L1+L2+L3=1, stored in PT(1:3,*)
!   NCORD=2 : unit coordinates (L1,L2) only, stored in PT(1:2,*); L3 omitted
!------------------------------------------------------------------------------
SUBROUTINE DQRULE(tq, IDEG, NQP, NCORD, PT, WT, iErr)

   implicit none

   class(GENERAL_QUAD_TYPE), intent(inOut) :: tQ
   integer(i4b), intent(in)  :: iDeg, nCord
   integer(i4b), intent(Out) :: nQp
   integer(i4b), intent(Out) :: iErr
   real(dp),     intent(out) :: PT(:,:), WT(:)

   real(dp)     :: sum
   integer(i4b) :: i, j, LDEG, ipt, iRule, kount

   ! NQPDEG(d) = number of quadrature points for polynomial degree d
   integer(i4b), parameter :: NQPDEG(17) = [1,3,4,6,7,12,13,16,19,25,27,33,37,42,48,52,61]
   ! LINES(d)  = number of distinct symmetry-class entries in the table for degree d
   integer(i4b), parameter :: LINES(17)  = [1,1,2,2,3,3,4,5,6,6,7,8,10,10,11,13,15]
   ! ISTART(d) = first index into the compact data arrays for degree d
   integer(i4b), parameter :: ISTART(17) = [1,2,3,5,7,10,13,17,22,28,34,41,49,59,69,80,93]
   ! KOUNTS(j) = symmetry multiplicity of entry j (1, 3, or 6)
   integer(i4b), parameter :: KOUNTS(107) = [ &
        1, 3, 1, 3, 3, 3, 1, 3, 3, 3, 3, 6, 1, 3, 3, 6, 1, 3, 3, 3, 6, 1, 3, 3, 3,  &
        3, 6, 1, 3, 3, 6, 6, 6, 3, 3, 3, 3, 3, 6, 6, 3, 3, 3, 3, 3, 6, 6, 6, 1, 3,  &
        3, 3, 3, 3, 3, 6, 6, 6, 3, 3, 3, 3, 3, 3, 6, 6, 6, 6, 3, 3, 3, 3, 3, 3, 6,  &
        6, 6, 6, 6, 1, 3, 3, 3, 3, 3, 3, 3, 6, 6, 6, 6, 6, 1, 3, 3, 3, 3, 3, 3, 3,  &
        3, 6, 6, 6, 6, 6, 6 ]

   !  Compact Dunavant table data: AW = weights, A1/A2/A3 = area coordinates.
   !  Each entry represents one symmetry class; KOUNTS(j) copies are generated.

   real(dp), parameter :: aW(107) = (/                                             &
      1.000000000000000d0,  0.333333333333333d0, -0.562500000000000d0,             &
      0.520833333333333d0,  0.223381589678011d0,  0.109951743655322d0,             &
      0.225000000000000d0,  0.132394152788506d0,  0.125939180544827d0,             &
      0.116786275726379d0,  0.050844906370207d0,  0.082851075618374d0,             &
     -0.149570044467682d0,  0.175615257433208d0,  0.053347235608838d0,             &
      0.077113760890257d0,  0.144315607677787d0,  0.095091634267285d0,             &
      0.103217370534718d0,  0.032458497623198d0,  0.027230314174435d0,             &
      0.097135796282799d0,  0.031334700227139d0,  0.077827541004774d0,             &
      0.079647738927210d0,  0.025577675658698d0,  0.043283539377289d0,             &
      0.090817990382754d0,  0.036725957756467d0,  0.045321059435528d0,             &
      0.072757916845420d0,  0.028327242531057d0,  0.009421666963733d0,             &
      0.000927006328961d0,  0.077149534914813d0,  0.059322977380774d0,             &
      0.036184540503418d0,  0.013659731002678d0,  0.052337111962204d0,             &
      0.020707659639141d0,  0.025731066440455d0,  0.043692544538038d0,             &
      0.062858224217885d0,  0.034796112930709d0,  0.006166261051559d0,             &
      0.040371557766381d0,  0.022356773202303d0,  0.017316231108659d0,             &
      0.052520923400802d0,  0.011280145209330d0,  0.031423518362454d0,             &
      0.047072502504194d0,  0.047363586536355d0,  0.031167529045794d0,             &
      0.007975771465074d0,  0.036848402728732d0,  0.017401463303822d0,             &
      0.015521786839045d0,  0.021883581369429d0,  0.032788353544125d0,             &
      0.051774104507292d0,  0.042162588736993d0,  0.014433699669777d0,             &
      0.004923403602400d0,  0.024665753212564d0,  0.038571510787061d0,             &
      0.014436308113534d0,  0.005010228838501d0,  0.001916875642849d0,             &
      0.044249027271145d0,  0.051186548718852d0,  0.023687735870688d0,             &
      0.013289775690021d0,  0.004748916608192d0,  0.038550072599593d0,             &
      0.027215814320624d0,  0.002182077366797d0,  0.021505319847731d0,             &
      0.007673942631049d0,  0.046875697427642d0,  0.006405878578585d0,             &
      0.041710296739387d0,  0.026891484250064d0,  0.042132522761650d0,             &
      0.030000266842773d0,  0.014200098925024d0,  0.003582462351273d0,             &
      0.032773147460627d0,  0.015298306248441d0,  0.002386244192839d0,             &
      0.019084792755899d0,  0.006850054546542d0,  0.033437199290803d0,             &
      0.005093415440507d0,  0.014670864527638d0,  0.024350878353672d0,             &
      0.031107550868969d0,  0.031257111218620d0,  0.024815654339665d0,             &
      0.014056073070557d0,  0.003194676173779d0,  0.008119655318993d0,             &
      0.026805742283163d0,  0.018459993210822d0,  0.008476868534328d0,             &
      0.018292796770025d0,  0.006665632004165d0 /)

   real(dp), parameter :: a1(107) = (/                                             &
      0.333333333333333d0,  0.666666666666667d0,  0.333333333333333d0,             &
      0.600000000000000d0,  0.108103018168070d0,  0.816847572980459d0,             &
      0.333333333333333d0,  0.059715871789770d0,  0.797426985353087d0,             &
      0.501426509658179d0,  0.873821971016996d0,  0.053145049844817d0,             &
      0.333333333333333d0,  0.479308067841920d0,  0.869739794195568d0,             &
      0.048690315425316d0,  0.333333333333333d0,  0.081414823414554d0,             &
      0.658861384496480d0,  0.898905543365938d0,  0.008394777409958d0,             &
      0.333333333333333d0,  0.020634961602525d0,  0.125820817014127d0,             &
      0.623592928761935d0,  0.910540973211095d0,  0.036838412054736d0,             &
      0.333333333333333d0,  0.028844733232685d0,  0.781036849029926d0,             &
      0.141707219414880d0,  0.025003534762686d0,  0.009540815400299d0,             &
     -0.069222096541517d0,  0.202061394068290d0,  0.593380199137435d0,             &
      0.761298175434837d0,  0.935270103777448d0,  0.050178138310495d0,             &
      0.021022016536166d0,  0.023565220452390d0,  0.120551215411079d0,             &
      0.457579229975768d0,  0.744847708916828d0,  0.957365299093579d0,             &
      0.115343494534698d0,  0.022838332222257d0,  0.025734050548330d0,             &
      0.333333333333333d0,  0.009903630120591d0,  0.062566729780852d0,             &
      0.170957326397447d0,  0.541200855914337d0,  0.771151009607340d0,             &
      0.950377217273082d0,  0.094853828379579d0,  0.018100773278807d0,             &
      0.022233076674090d0,  0.022072179275643d0,  0.164710561319092d0,             &
      0.453044943382323d0,  0.645588935174913d0,  0.876400233818255d0,             &
      0.961218077502598d0,  0.057124757403648d0,  0.092916249356972d0,             &
      0.014646950055654d0,  0.001268330932872d0, -0.013945833716486d0,             &
      0.137187291433955d0,  0.444612710305711d0,  0.747070217917492d0,             &
      0.858383228050628d0,  0.962069659517853d0,  0.133734161966621d0,             &
      0.036366677396917d0, -0.010174883126571d0,  0.036843869875878d0,             &
      0.012459809331199d0,  0.333333333333333d0,  0.005238916103123d0,             &
      0.173061122901295d0,  0.059082801866017d0,  0.518892500060958d0,             &
      0.704068411554854d0,  0.849069624685052d0,  0.966807194753950d0,             &
      0.103575692245252d0,  0.020083411655416d0, -0.004341002614139d0,             &
      0.041941786468010d0,  0.014317320230681d0,  0.333333333333333d0,             &
      0.005658918886452d0,  0.035647354750751d0,  0.099520061958437d0,             &
      0.199467521245206d0,  0.495717464058095d0,  0.675905990683077d0,             &
      0.848248235478508d0,  0.968690546064356d0,  0.010186928826919d0,             &
      0.135440871671036d0,  0.054423924290583d0,  0.012868560833637d0,             &
      0.067165782413524d0,  0.014663182224828d0 /)

   real(dp), parameter :: a2(107) = (/                                             &
      0.333333333333333d0,  0.166666666666667d0,  0.333333333333333d0,             &
      0.200000000000000d0,  0.445948490915965d0,  0.091576213509771d0,             &
      0.333333333333333d0,  0.470142064105115d0,  0.101286507323456d0,             &
      0.249286745170910d0,  0.063089014491502d0,  0.310352451033784d0,             &
      0.333333333333333d0,  0.260345966079040d0,  0.065130102902216d0,             &
      0.312865496004874d0,  0.333333333333333d0,  0.459292588292723d0,             &
      0.170569307751760d0,  0.050547228317031d0,  0.263112829634638d0,             &
      0.333333333333333d0,  0.489682519198738d0,  0.437089591492937d0,             &
      0.188203535619033d0,  0.044729513394453d0,  0.221962989160766d0,             &
      0.333333333333333d0,  0.485577633383657d0,  0.109481575485037d0,             &
      0.307939838764121d0,  0.246672560639903d0,  0.066803251012200d0,             &
      0.534611048270758d0,  0.398969302965855d0,  0.203309900431282d0,             &
      0.119350912282581d0,  0.032364948111276d0,  0.356620648261293d0,             &
      0.171488980304042d0,  0.488217389773805d0,  0.439724392294460d0,             &
      0.271210385012116d0,  0.127576145541586d0,  0.021317350453210d0,             &
      0.275713269685514d0,  0.281325580989940d0,  0.116251915907597d0,             &
      0.333333333333333d0,  0.495048184939705d0,  0.468716635109574d0,             &
      0.414521336801277d0,  0.229399572042831d0,  0.114424495196330d0,             &
      0.024811391363459d0,  0.268794997058761d0,  0.291730066734288d0,             &
      0.126357385491669d0,  0.488963910362179d0,  0.417644719340454d0,             &
      0.273477528308839d0,  0.177205532412543d0,  0.061799883090873d0,             &
      0.019390961248701d0,  0.172266687821356d0,  0.336861459796345d0,             &
      0.298372882136258d0,  0.118974497696957d0,  0.506972916858243d0,             &
      0.431406354283023d0,  0.277693644847144d0,  0.126464891041254d0,             &
      0.070808385974686d0,  0.018965170241073d0,  0.261311371140087d0,             &
      0.388046767090269d0,  0.285712220049916d0,  0.215599664072284d0,             &
      0.103575616576386d0,  0.333333333333333d0,  0.497380541948438d0,             &
      0.413469438549352d0,  0.470458599066991d0,  0.240553749969521d0,             &
      0.147965794222573d0,  0.075465187657474d0,  0.016596402623025d0,             &
      0.296555596579887d0,  0.337723063403079d0,  0.204748281642812d0,             &
      0.189358492130623d0,  0.085283615682657d0,  0.333333333333333d0,             &
      0.497170540556774d0,  0.482176322624625d0,  0.450239969020782d0,             &
      0.400266239377397d0,  0.252141267970953d0,  0.162047004658461d0,             &
      0.075875882260746d0,  0.015654726967822d0,  0.334319867363658d0,             &
      0.292221537796944d0,  0.319574885423190d0,  0.190704224192292d0,             &
      0.180483211648746d0,  0.080711313679564d0 /)

   real(dp), parameter :: a3(107) = (/                                             &
      0.333333333333333d0,  0.166666666666667d0,  0.333333333333333d0,             &
      0.200000000000000d0,  0.445948490915965d0,  0.091576213509771d0,             &
      0.333333333333333d0,  0.470142064105115d0,  0.101286507323456d0,             &
      0.249286745170910d0,  0.063089014491502d0,  0.636502499121399d0,             &
      0.333333333333333d0,  0.260345966079040d0,  0.065130102902216d0,             &
      0.638444188569810d0,  0.333333333333333d0,  0.459292588292723d0,             &
      0.170569307751760d0,  0.050547228317031d0,  0.728492392955404d0,             &
      0.333333333333333d0,  0.489682519198738d0,  0.437089591492937d0,             &
      0.188203535619033d0,  0.044729513394453d0,  0.741198598784498d0,             &
      0.333333333333333d0,  0.485577633383657d0,  0.109481575485037d0,             &
      0.550352941820999d0,  0.728323904597411d0,  0.923655933587500d0,             &
      0.534611048270758d0,  0.398969302965855d0,  0.203309900431282d0,             &
      0.119350912282581d0,  0.032364948111276d0,  0.593201213428213d0,             &
      0.807489003159792d0,  0.488217389773805d0,  0.439724392294460d0,             &
      0.271210385012116d0,  0.127576145541586d0,  0.021317350453210d0,             &
      0.608943235779788d0,  0.695836086787803d0,  0.858014033544073d0,             &
      0.333333333333333d0,  0.495048184939705d0,  0.468716635109574d0,             &
      0.414521336801277d0,  0.229399572042831d0,  0.114424495196330d0,             &
      0.024811391363459d0,  0.636351174561660d0,  0.690169159986905d0,             &
      0.851409537834241d0,  0.488963910362179d0,  0.417644719340454d0,             &
      0.273477528308839d0,  0.177205532412543d0,  0.061799883090873d0,             &
      0.019390961248701d0,  0.770608554774996d0,  0.570222290846683d0,             &
      0.686980167808088d0,  0.879757171370171d0,  0.506972916858243d0,             &
      0.431406354283023d0,  0.277693644847144d0,  0.126464891041254d0,             &
      0.070808385974686d0,  0.018965170241073d0,  0.604954466893291d0,             &
      0.575586555512814d0,  0.724462663076655d0,  0.747556466051838d0,             &
      0.883964574092416d0,  0.333333333333333d0,  0.497380541948438d0,             &
      0.413469438549352d0,  0.470458599066991d0,  0.240553749969521d0,             &
      0.147965794222573d0,  0.075465187657474d0,  0.016596402623025d0,             &
      0.599868711174861d0,  0.642193524941505d0,  0.799592720971327d0,             &
      0.768699721401368d0,  0.900399064086661d0,  0.333333333333333d0,             &
      0.497170540556774d0,  0.482176322624625d0,  0.450239969020782d0,             &
      0.400266239377397d0,  0.252141267970953d0,  0.162047004658461d0,             &
      0.075875882260746d0,  0.015654726967822d0,  0.655493203809423d0,             &
      0.572337590532020d0,  0.626001190286228d0,  0.796427214974071d0,             &
      0.752351005937729d0,  0.904625504095608d0 /)

   !----- begin executable code -----

   iErr = 1   ! default: error (set to 0 only on successful return)

   LDEG = IDEG

   IF (NQP .EQ. 0) THEN
      ! Degree control: look up nQp from NQPDEG
      IF (IDEG .EQ. 0) NQP = 1
      IF (IDEG .LT. 0 .OR. IDEG .GT. 17) GOTO 9000
      NQP = NQPDEG(IDEG)
   ELSE
      ! NQP control: find the matching degree in NQPDEG
      LDEG = 0
      DO 10 I = 1, 17
         IF (NQP .EQ. NQPDEG(I)) LDEG = I
10    CONTINUE
      IF (LDEG .EQ. 0) GOTO 9000
   ENDIF

   ! Expand the compact symmetry-class table to the full NQP-point rule
   IPT   = ISTART(LDEG) - 1
   IRULE = 0
   SUM   = 0.D0

   DO 20 I = 1, LINES(LDEG)
      J     = IPT + I
      KOUNT = KOUNTS(J)
      IRULE = IRULE + 1
      SUM   = SUM + AW(J)*KOUNT
      WT(IRULE)   = AW(J)
      PT(1,IRULE) = A1(J)
      PT(2,IRULE) = A2(J)
      IF (NCORD .EQ. 3) PT(3,IRULE) = A3(J)

      IF (KOUNT .GE. 3) THEN
         ! Generate 2 additional permutations for KOUNT=3 class: (A3,A1), (A2,A3)
         IRULE = IRULE + 1
         WT(IRULE)   = AW(J)
         PT(1,IRULE) = A3(J);  PT(2,IRULE) = A1(J)
         IF (NCORD .EQ. 3) PT(3,IRULE) = A2(J)
         IRULE = IRULE + 1
         WT(IRULE)   = AW(J)
         PT(1,IRULE) = A2(J);  PT(2,IRULE) = A3(J)
         IF (NCORD .EQ. 3) PT(3,IRULE) = A1(J)
      ENDIF

      IF (KOUNT .EQ. 6) THEN
         ! Generate 3 additional permutations for KOUNT=6 class: (A1,A3), (A3,A2), (A2,A1)
         IRULE = IRULE + 1
         WT(IRULE)   = AW(J)
         PT(1,IRULE) = A1(J);  PT(2,IRULE) = A3(J)
         IF (NCORD .EQ. 3) PT(3,IRULE) = A2(J)
         IRULE = IRULE + 1
         WT(IRULE)   = AW(J)
         PT(1,IRULE) = A3(J);  PT(2,IRULE) = A2(J)
         IF (NCORD .EQ. 3) PT(3,IRULE) = A1(J)
         IRULE = IRULE + 1
         WT(IRULE)   = AW(J)
         PT(1,IRULE) = A2(J);  PT(2,IRULE) = A1(J)
         IF (NCORD .EQ. 3) PT(3,IRULE) = A3(J)
      ENDIF
20 END DO

   iErr = 0
   RETURN

9000 continue   ! invalid IDEG or NQP -- iErr remains 1

END subroutine DQRULE

!==============================================================================
!  GAULEG -- Gauss-Legendre abscissae and weights (Numerical Recipes)
!==============================================================================

!------------------------------------------------------------------------------
!  GAULEG: compute the N-point Gauss-Legendre quadrature rule on [X1, X2].
!
!  Source: Numerical Recipes in Fortran, adapted to F90 style.
!
!  Algorithm:
!   1. Exploit symmetry: only M = (N+1)/2 distinct roots are computed;
!      each gives a symmetric pair X(I), X(N+1-I) and equal weight W(I).
!   2. Initial estimate for root I:
!        z = cos( pi * (I - 0.25) / (N + 0.5) )
!      (standard approximation for the I-th Legendre root)
!   3. Newton-Raphson iteration until |z - z_old| < EPS:
!        Evaluate P_N(z) and P'_N(z) via the 3-term recurrence:
!          P_0 = 1,  P_1 = z
!          P_j = ((2j-1)*z*P_{j-1} - (j-1)*P_{j-2}) / j
!        Derivative:  P'_N = N*(z*P_N - P_{N-1}) / (z^2 - 1)
!        Update:      z = z - P_N(z) / P'_N(z)
!   4. Map from [-1,1] to [X1,X2]:
!        X(I) = XM - XL*z,   X(N+1-I) = XM + XL*z
!        W(I) = W(N+1-I) = 2*XL / ((1-z^2) * (P'_N)^2)
!      where XM = (X1+X2)/2, XL = (X2-X1)/2.
!
!  Precision:
!   Internal variables (XM, XL, Z, P1..P3, PP) are real(8) to ensure
!   Newton convergence to EPS = 3e-14.  Output X and W are stored as
!   real(dp) = real32 (working precision of the calling code).
!
!  For NeoMoM: called with N=16, X1=0.0, X2=1.0 to produce the 16-point
!  rule used in zfill_m.f90 for NEAR-field segment pair integrations.
!------------------------------------------------------------------------------
   pure SUBROUTINE GAULEG(GQ, X1, X2, X, W, N)
      class(GENERAL_QUAD_TYPE), intent(in) :: GQ
      integer(i4b), intent(in)  :: N
      real(dp),     intent(in)  :: X1, X2      ! integration interval [X1, X2]
      real(dp),     intent(out) :: X(N), W(N)  ! abscissae and weights

      real(dp), PARAMETER :: EPS = 3.D-14     ! Newton convergence tolerance (double)

      integer(i4b) :: M, I, J
      real(8)      :: XM, XL, PP, Z, Z1, P1, P2, P3   ! real(8) for Newton accuracy

      M  = (N + 1)/2                 ! only half the roots need computing (symmetry)
      XM = 0.5D0*(X2 + X1)           ! midpoint of interval
      XL = 0.5D0*(X2 - X1)           ! half-length of interval

      DO 12 I = 1, M
         ! Initial estimate: I-th root of P_N on (-1,1)
         Z = cos(3.1415926535897932384626D0*(I - .25D0)/(N + .5D0))

1        CONTINUE   ! Newton-Raphson iteration
         P1 = 1.D0
         P2 = 0.D0
         DO 11 J = 1, N
            P3 = P2
            P2 = P1
            P1 = ((2.D0*J - 1.D0)*Z*P2 - (J - 1.D0)*P3)/J  ! P_J via recurrence
11       CONTINUE
         ! Derivative P'_N(z) = N*(z*P_N - P_{N-1}) / (z^2 - 1)
         PP = N*(Z*P1 - P2)/(Z*Z - 1.D0)
         Z1 = Z
         Z  = Z1 - P1/PP             ! Newton update
         IF (ABS(Z - Z1) .GT. EPS) GO TO 1   ! iterate until converged

         ! Map converged root Z (on [-1,1]) to [X1,X2] and store symmetric pair
         X(I)         = XM - XL*Z
         X(N + 1 - I) = XM + XL*Z
         W(I)         = 2.D0*XL/((1.D0 - Z*Z)*PP*PP)
         W(N + 1 - I) = W(I)         ! symmetric weights are equal
12    END DO

   END subroutine GAULEG

end Module quadrature_v2_m
