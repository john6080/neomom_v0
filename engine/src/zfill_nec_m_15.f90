module zfill_nec_m

!==============================================================================
!  zfill_nec_m — NEC5-style wire-wire interaction fill (companion to zfill_m)
!
!  Galerkin double-integral fill, same architecture as zfill_m::fill_matrix
!  (per Burke, "Accuracy of Reduced and Extended Thin-Wire Kernels",
!  LLNL-PROC-409033: NEC-5 is a mixed-potential code with triangular/
!  roof-top basis functions, not point-matched like NEC-4).
!
!  What distinguishes NEC5's wire-wire interaction is the KERNEL: a choice
!  of RTWK (reduced thin-wire kernel) or ETWK (extended thin-wire kernel).
!  Both approximate the same exact kernel
!
!      K(rho,z) = INT_{-D/2}^{D/2} INT_{-pi}^{pi} exp(-jkR)/R  dphi dz'      (Burke eq.1)
!      R = sqrt(rho^2 + a^2 + (z-z')^2 - 2*a*rho*cos(phi))
!
!  RTWK (Burke eq. 3): evaluation points on-axis, current as a filament,
!      K0(rho,z) = 2*pi * INT e^{-jkR0}/R0 dz',  R0 = sqrt(rho^2+a^2+(z-z')^2)
!  This is the "R -> sqrt(|dr|^2+a^2)" reduced-kernel offset used below in
!  source_gauss_nec, applied only to non-FAR pairs -- softening 1/R on
!  genuinely far cross-wire pairs weakens mutual-coupling cancellation and
!  inflates net reactance for closely-spaced parallel wires (see
!  source_gauss_nec).
!
!  ETWK (Burke eq. 2, 4, 5): removes the singular 1/R term from a series
!  expansion of the exponential and integrates THAT term analytically over
!  z' (closed form, eq. 4/5), leaving only a well-behaved numerical
!  integral. Burke shows RTWK's self-term error is poor once Delta/a is
!  order 1 or less, and demonstrates NEC-5 current going unstable with
!  RTWK at small Delta/a (Fig. 2) while ETWK stays stable to very small
!  Delta/a (Fig. 3). That is precisely the segment-length/radius regime at
!  a bent junction with short segments -- which is why ETWK, not just the
!  RTWK offset, is the more targeted candidate for your NEAR-branch
!  investigation.
!
!  PLAIN-LANGUAGE SUMMARY (RTWK vs ETWK):
!
!  RTWK -- Reduced Thin-Wire Kernel. The older, simpler approximation.
!  Current is modeled as a filament on the wire's axis; the field is
!  evaluated with the wire radius folded in only as an offset under the
!  square root (R0 = sqrt(rho^2+a^2+(z-z')^2)) rather than a true singular
!  axis-to-axis distance. A single 1-D integral over the source segment,
!  cheap, and exactly what Gibson's closed-form self term (zfill_m) already
!  computes. Degrades once segment-length/radius (Delta/a) gets down around
!  1 or less -- e.g. a short segment near a bent junction, or a tightly-
!  spaced parallel wire.
!
!  ETWK -- Extended Thin-Wire Kernel. A more accurate treatment for that
!  same small-Delta/a regime. Starts from the exact kernel (current on the
!  actual cylindrical surface, integrated around the circumference AND
!  along the axis), splits it into a well-behaved remainder (numerical) and
!  the genuinely singular 1/R part (pulled out and integrated ANALYTICALLY
!  in closed form -- the log(...) expressions in etwk_core, Burke eq.4/5).
!  Stays numerically stable and accurate even as segments get very short
!  relative to the wire radius, exactly where RTWK becomes unreliable
!  (Burke's NEC-5 dipole current instability example, Fig.2 vs Fig.3).
!
!  HOW THIS MODULE ROUTES BETWEEN THEM:
!   - selfKernel = KERNEL_RTWK  -> Gibson's closed form (self term only).
!   - selfKernel = KERNEL_ETWK  -> Burke closed-form singularity extraction
!                                   (self term).
!   - isNearTouching pairs (shares a node, or axis gap within
!     C3_radMult*wireRadius) -> ALWAYS ETWK via source_pair_etwk,
!     regardless of selfKernel -- that flag only ever governs the self term.
!   - Non-touching pairs -> RTWK-style plain quadrature, NOT ETWK (applying
!     the singularity-subtracted ETWK formula there overcorrects). The
!     quadrature order is graduated by select_nQ (NQ_FAR/NQ_NEAR/NQ_64/
!     NQ_128), based on the true seg_seg_distance gap-to-length ratio.
!
!  EXTENSIONS BEYOND THE PAPER:
!   - Eq. 1-5 (RTWK, ETWK, the closed-form log-singularity extraction) are
!     Burke's, reproduced directly for the self term. Nothing in that
!     derivation requires the field point to be ON the source segment --
!     (rho,z) is just "field point in cylindrical coordinates relative to a
!     straight source segment's axis" -- so the same closed form applies to
!     a different segment's field point too, with rho the true perpendicular
!     distance from the test point to the source segment's axis line. This
!     generalization to NEAR (node-sharing, different-segment) pairs is
!     applied in source_pair_etwk below; see that routine's header for the
!     projection geometry. Burke's own numerical results only cover
!     self-term / far-pair convergence, not adjacent-segment near terms.
!   - Burke's eq. 2/4/5 derivation is for constant source density. The
!     rooftop basis needs the same kernel weighted by a linear ramp
!     scalar_q(z') = z'/L or (L-z')/L, which Burke's closed form does not
!     directly cover. The weighted (Ivec) piece uses standard singularity
!     subtraction: the ramp weight is evaluated at the source-segment
!     coordinate nearest the singularity (the axial projection of the test
!     point, not the test point's own position), and the smooth remainder is
!     quadratured as usual -- flagged in etwk_core below.
!   - FAR pairs use the plain RTWK offset (source_gauss_nec) -- no
!     rapid-variation concern there, the extra machinery isn't worth it.
!
!  Reference: G. J. Burke, "Accuracy of Reduced and Extended Thin-Wire
!  Kernels," LLNL-PROC-409033, ACES 2009.
!==============================================================================

   use basic_header_m
   use nodes_wires_segments_m, only: SEGMENT_TYPE
   use basis_builder_m

   implicit none; private

   public :: NEC_ZFILL_TYPE
   public :: KERNEL_RTWK, KERNEL_ETWK, KERNEL_EXACT, KERNEL_BARE

   integer, parameter :: KERNEL_RTWK = 1
   integer, parameter :: KERNEL_ETWK = 2    ! closed-form singularity
                                             ! extraction (Burke eq.4/5).
                                             ! Approximates the true kernel's
                                             ! phi-dependence by evaluating at
                                             ! phi=pi/2 and scaling by 2*pi,
                                             ! which underestimates the true
                                             ! kernel by up to ~17% when
                                             ! rho~a -- see KERNEL_EXACT.
   integer, parameter :: KERNEL_EXACT = 3   ! direct double (z',phi) quadrature
                                             ! of the true kernel -- see
                                             ! exact_core header. No closed-
                                             ! form approximation at all.
   integer, parameter :: KERNEL_BARE = 4    ! bare R = |dr|, no offset of any
                                             ! kind. NOTE: KERNEL_RTWK in this
                                             ! module's source_gauss_nec is
                                             ! NOT the same thing -- it adds
                                             ! a^2 whenever the quadrature
                                             ! order is elevated above NQ_FAR.

   integer, parameter :: NQ_FAR  = 4
   integer, parameter :: NQ_NEAR = 16
   integer, parameter :: NQ_64   = 64    ! third rung of the distance-ratio
                                          ! quadrature ladder -- see select_nQ.
   integer, parameter :: NQ_128  = 128   ! fourth (top) rung.
   integer, parameter :: NQ_PHI  = 16    ! phi-integral quadrature for ETWK
   integer, parameter :: NQ_EXACT = 32   ! double quadrature order for
                                          ! KERNEL_EXACT, both z' and phi.
                                          ! The integrand is smooth (R>=a
                                          ! always, no true singularity), so
                                          ! this is generous headroom, not a
                                          ! minimum-required order.

   real, parameter :: XI4(4) = [ 0.069431844, 0.330009478, 0.669990522, 0.930568156 ]
   real, parameter :: W4(4)  = [ 0.173927423, 0.326072577, 0.326072577, 0.173927423 ]

   real, parameter :: XI16(16) = [ &
      5.2995323E-03, 2.7712489E-02, 6.7184396E-02, 0.1222978, 0.1910619, &
      0.2709916,     0.3591982,     0.4524938,     0.5475063, 0.6408018, &
      0.7290084,     0.8089381,     0.8777022,     0.9328156, 0.9722875, &
      0.9947005 ]

   real, parameter :: W16(16) = [ &
      1.3576230E-02, 3.1126762E-02, 4.7579255E-02, 6.2314484E-02, 7.4797995E-02, &
      8.4578261E-02, 9.1301709E-02, 9.4725303E-02, 9.4725303E-02, 9.1301709E-02, &
      8.4578261E-02, 7.4797995E-02, 6.2314484E-02, 4.7579255E-02, 3.1126762E-02, &
      1.3576230E-02 ]

   ! 32-point Gauss-Legendre on [0,1], generated directly (numpy
   ! leggauss) rather than hand-transcribed, for KERNEL_EXACT's double
   ! (z',phi) quadrature.
   real, parameter :: XI32(32) = [ &
      1.3680690753E-03, 7.1942442274E-03, 1.7618872206E-02, 3.2546962031E-02, &
      5.1839422117E-02, 7.5316193134E-02, 1.0275810202E-01, 1.3390894063E-01, &
      1.6847786653E-01, 2.0614212138E-01, 2.4655004553E-01, 2.8932436193E-01, &
      3.3406569886E-01, 3.8035631887E-01, 4.2776401921E-01, 4.7584616716E-01, &
      5.2415383284E-01, 5.7223598079E-01, 6.1964368113E-01, 6.6593430114E-01, &
      7.1067563807E-01, 7.5344995447E-01, 7.9385787862E-01, 8.3152213347E-01, &
      8.6609105937E-01, 8.9724189798E-01, 9.2468380687E-01, 9.4816057788E-01, &
      9.6745303797E-01, 9.8238112779E-01, 9.9280575577E-01, 9.9863193092E-01 ]

   real, parameter :: W32(32) = [ &
      3.5093050047E-03, 8.1371973655E-03, 1.2696032655E-02, 1.7136931457E-02, &
      2.1417949011E-02, 2.5499029631E-02, 2.9342046739E-02, 3.2911111388E-02, &
      3.6172897054E-02, 3.9096947894E-02, 4.1655962113E-02, 4.3826046502E-02, &
      4.5586939348E-02, 4.6922199540E-02, 4.7819360040E-02, 4.8270044257E-02, &
      4.8270044257E-02, 4.7819360040E-02, 4.6922199540E-02, 4.5586939348E-02, &
      4.3826046502E-02, 4.1655962113E-02, 3.9096947894E-02, 3.6172897054E-02, &
      3.2911111388E-02, 2.9342046739E-02, 2.5499029631E-02, 2.1417949011E-02, &
      1.7136931457E-02, 1.2696032655E-02, 8.1371973655E-03, 3.5093050047E-03 ]

   ! 64- and 128-point Gauss-Legendre on [0,1] (numpy leggauss), the
   ! third and fourth rungs of the distance-ratio quadrature ladder
   ! used for closely-spaced NEAR pairs -- see select_nQ.
   real, parameter :: XI64(64) = [ &
      3.4747913211E-04, 1.8299416140E-03, 4.4933142616E-03, 8.3318730577E-03, &
      1.3336586105E-02, 1.9495600174E-02, 2.6794312571E-02, 3.5215413934E-02, &
      4.4738931461E-02, 5.5342277002E-02, 6.7000300923E-02, 7.9685351874E-02, &
      9.3367342439E-02, 1.0801382053E-01, 1.2359004637E-01, 1.4005907491E-01, &
      1.5738184347E-01, 1.7551726437E-01, 1.9442232241E-01, 2.1405217690E-01, &
      2.3436026799E-01, 2.5529842715E-01, 2.7681699137E-01, 2.9886492102E-01, &
      3.2138992083E-01, 3.4433856400E-01, 3.6765641890E-01, 3.9128817813E-01, &
      4.1517778979E-01, 4.3926859035E-01, 4.6350343911E-01, 4.8782485367E-01, &
      5.1217514633E-01, 5.3649656089E-01, 5.6073140965E-01, 5.8482221021E-01, &
      6.0871182187E-01, 6.3234358110E-01, 6.5566143600E-01, 6.7861007917E-01, &
      7.0113507898E-01, 7.2318300863E-01, 7.4470157285E-01, 7.6563973201E-01, &
      7.8594782310E-01, 8.0557767759E-01, 8.2448273563E-01, 8.4261815653E-01, &
      8.5994092509E-01, 8.7640995363E-01, 8.9198617947E-01, 9.0663265756E-01, &
      9.2031464813E-01, 9.3299969908E-01, 9.4465772300E-01, 9.5526106854E-01, &
      9.6478458607E-01, 9.7320568743E-01, 9.8050439983E-01, 9.8666341389E-01, &
      9.9166812694E-01, 9.9550668574E-01, 9.9817005839E-01, 9.9965252087E-01 ]

   real, parameter :: W64(64) = [ &
      8.9164036085E-04, 2.0735166303E-03, 3.2522289845E-03, 4.4233799132E-03, &
      5.5840697301E-03, 6.7315239484E-03, 7.8630152380E-03, 8.9758578878E-03, &
      1.0067411577E-02, 1.1135086904E-02, 1.2176351284E-02, 1.3188734858E-02, &
      1.4169836307E-02, 1.5117328536E-02, 1.6028964177E-02, 1.6902580919E-02, &
      1.7736106628E-02, 1.8527564270E-02, 1.9275076589E-02, 1.9976870566E-02, &
      2.0631281621E-02, 2.1236757562E-02, 2.1791862265E-02, 2.2295279082E-02, &
      2.2745813964E-02, 2.3142398291E-02, 2.3484091408E-02, 2.3770082857E-02, &
      2.3999694298E-02, 2.4172381117E-02, 2.4287733721E-02, 2.4345478505E-02, &
      2.4345478505E-02, 2.4287733721E-02, 2.4172381117E-02, 2.3999694298E-02, &
      2.3770082857E-02, 2.3484091408E-02, 2.3142398291E-02, 2.2745813964E-02, &
      2.2295279082E-02, 2.1791862265E-02, 2.1236757562E-02, 2.0631281621E-02, &
      1.9976870566E-02, 1.9275076589E-02, 1.8527564270E-02, 1.7736106628E-02, &
      1.6902580919E-02, 1.6028964177E-02, 1.5117328536E-02, 1.4169836307E-02, &
      1.3188734858E-02, 1.2176351284E-02, 1.1135086904E-02, 1.0067411577E-02, &
      8.9758578878E-03, 7.8630152380E-03, 6.7315239484E-03, 5.5840697301E-03, &
      4.4233799132E-03, 3.2522289845E-03, 2.0735166303E-03, 8.9164036085E-04 ]

   real, parameter :: XI128(128) = [ &
      8.7556026434E-05, 4.6127001131E-04, 1.1333756872E-03, 2.1036207325E-03, &
      3.3714435499E-03, 4.9360907541E-03, 6.7966286377E-03, 8.9519457821E-03, &
      1.1400754268E-02, 1.4141590626E-02, 1.7172816784E-02, 2.0492621073E-02, &
      2.4099019329E-02, 2.7989856085E-02, 3.2162805861E-02, 3.6615374561E-02, &
      4.1344900960E-02, 4.6348558299E-02, 5.1623355975E-02, 5.7166141327E-02, &
      6.2973601521E-02, 6.9042265530E-02, 7.5368506211E-02, 8.1948542470E-02, &
      8.8778441522E-02, 9.5854121246E-02, 1.0317135262E-01, 1.1072576225E-01, &
      1.1851283498E-01, 1.2652791660E-01, 1.3476621663E-01, 1.4322281116E-01, &
      1.5189264582E-01, 1.6077053878E-01, 1.6985118386E-01, 1.7912915372E-01, &
      1.8859890304E-01, 1.9825477192E-01, 2.0809098919E-01, 2.1810167589E-01, &
      2.2828084879E-01, 2.3862242397E-01, 2.4912022043E-01, 2.5976796380E-01, &
      2.7055929008E-01, 2.8148774948E-01, 2.9254681022E-01, 3.0372986248E-01, &
      3.1503022233E-01, 3.2644113570E-01, 3.3795578249E-01, 3.4956728056E-01, &
      3.6126868991E-01, 3.7305301679E-01, 3.8491321789E-01, 3.9684220455E-01, &
      4.0883284701E-01, 4.2087797864E-01, 4.3297040027E-01, 4.4510288444E-01, &
      4.5726817975E-01, 4.6945901520E-01, 4.8166810452E-01, 4.9388815052E-01, &
      5.0611184948E-01, 5.1833189548E-01, 5.3054098480E-01, 5.4273182025E-01, &
      5.5489711556E-01, 5.6702959973E-01, 5.7912202136E-01, 5.9116715299E-01, &
      6.0315779545E-01, 6.1508678211E-01, 6.2694698321E-01, 6.3873131009E-01, &
      6.5043271944E-01, 6.6204421751E-01, 6.7355886430E-01, 6.8496977767E-01, &
      6.9627013752E-01, 7.0745318978E-01, 7.1851225052E-01, 7.2944070992E-01, &
      7.4023203620E-01, 7.5087977957E-01, 7.6137757603E-01, 7.7171915121E-01, &
      7.8189832411E-01, 7.9190901081E-01, 8.0174522808E-01, 8.1140109696E-01, &
      8.2087084628E-01, 8.3014881614E-01, 8.3922946122E-01, 8.4810735418E-01, &
      8.5677718884E-01, 8.6523378337E-01, 8.7347208340E-01, 8.8148716502E-01, &
      8.8927423775E-01, 8.9682864738E-01, 9.0414587875E-01, 9.1122155848E-01, &
      9.1805145753E-01, 9.2463149379E-01, 9.3095773447E-01, 9.3702639848E-01, &
      9.4283385867E-01, 9.4837664402E-01, 9.5365144170E-01, 9.5865509904E-01, &
      9.6338462544E-01, 9.6783719414E-01, 9.7201014392E-01, 9.7590098067E-01, &
      9.7950737893E-01, 9.8282718322E-01, 9.8585840937E-01, 9.8859924573E-01, &
      9.9104805422E-01, 9.9320337136E-01, 9.9506390925E-01, 9.9662855645E-01, &
      9.9789637927E-01, 9.9886662431E-01, 9.9953872999E-01, 9.9991244397E-01 ]

   real, parameter :: W128(128) = [ &
      2.2469048014E-04, 5.2290633967E-04, 8.2125150933E-04, 1.1191442155E-03, &
      1.4163757357E-03, 1.7127630205E-03, 2.0081274919E-03, 2.3022921284E-03, &
      2.5950809163E-03, 2.8863187714E-03, 3.1758315809E-03, 3.4634462834E-03, &
      3.7489909628E-03, 4.0322949452E-03, 4.3131888993E-03, 4.5915049358E-03, &
      4.8670767075E-03, 5.1397395079E-03, 5.4093303698E-03, 5.6756881620E-03, &
      5.9386536864E-03, 6.1980697720E-03, 6.4537813696E-03, 6.7056356443E-03, &
      6.9534820665E-03, 7.1971725021E-03, 7.4365613011E-03, 7.6715053844E-03, &
      7.9018643297E-03, 8.1275004549E-03, 8.3482789008E-03, 8.5640677116E-03, &
      8.7747379136E-03, 8.9801635925E-03, 9.1802219687E-03, 9.3747934703E-03, &
      9.5637618050E-03, 9.7470140294E-03, 9.9244406164E-03, 1.0095935521E-02, &
      1.0261396243E-02, 1.0420723890E-02, 1.0573823234E-02, 1.0720602770E-02, &
      1.0860974769E-02, 1.0994855334E-02, 1.1122164447E-02, 1.1242826016E-02, &
      1.1356767925E-02, 1.1463922072E-02, 1.1564224412E-02, 1.1657614997E-02, &
      1.1744038008E-02, 1.1823441792E-02, 1.1895778891E-02, 1.1961006068E-02, &
      1.2019084341E-02, 1.2069978995E-02, 1.2113659611E-02, 1.2150100084E-02, &
      1.2179278632E-02, 1.2201177817E-02, 1.2215784549E-02, 1.2223090098E-02, &
      1.2223090098E-02, 1.2215784549E-02, 1.2201177817E-02, 1.2179278632E-02, &
      1.2150100084E-02, 1.2113659611E-02, 1.2069978995E-02, 1.2019084341E-02, &
      1.1961006068E-02, 1.1895778891E-02, 1.1823441792E-02, 1.1744038008E-02, &
      1.1657614997E-02, 1.1564224412E-02, 1.1463922072E-02, 1.1356767925E-02, &
      1.1242826016E-02, 1.1122164447E-02, 1.0994855334E-02, 1.0860974769E-02, &
      1.0720602770E-02, 1.0573823234E-02, 1.0420723890E-02, 1.0261396243E-02, &
      1.0095935521E-02, 9.9244406164E-03, 9.7470140294E-03, 9.5637618050E-03, &
      9.3747934703E-03, 9.1802219687E-03, 8.9801635925E-03, 8.7747379136E-03, &
      8.5640677116E-03, 8.3482789008E-03, 8.1275004549E-03, 7.9018643297E-03, &
      7.6715053844E-03, 7.4365613011E-03, 7.1971725021E-03, 6.9534820665E-03, &
      6.7056356443E-03, 6.4537813696E-03, 6.1980697720E-03, 5.9386536864E-03, &
      5.6756881620E-03, 5.4093303698E-03, 5.1397395079E-03, 4.8670767075E-03, &
      4.5915049358E-03, 4.3131888993E-03, 4.0322949452E-03, 3.7489909628E-03, &
      3.4634462834E-03, 3.1758315809E-03, 2.8863187714E-03, 2.5950809163E-03, &
      2.3022921284E-03, 2.0081274919E-03, 1.7127630205E-03, 1.4163757357E-03, &
      1.1191442155E-03, 8.2125150933E-04, 5.2290633967E-04, 2.2469048014E-04 ]

!------------------------------------------------------------------------------
   type :: NEC_ZFILL_TYPE
      ! Defaults reproduce original zfill_m: RTWK self term (Gibson closed
      ! form), BARE near-pairs (no offset). ETWK/EXACT self and ETWK/EXACT/
      ! RTWK near-pair kernels are selectable alternatives -- see the
      ! KERNEL_* parameter comments above for what each does and when it's
      ! more accurate.
      integer :: selfKernel = KERNEL_RTWK    ! RTWK / ETWK / EXACT
      integer :: nearKernel = KERNEL_BARE    ! BARE / RTWK / ETWK / EXACT --
                                              ! RTWK here means bare + a^2
                                              ! floor, not a plain match to
                                              ! original zfill_m.

      ! Node-sharing/surface-touching threshold for isNearTouching -- see
      ! gap_within_radius. NEAR-pair quadrature order itself is chosen by
      ! select_nQ (purely geometric, no configuration needed).
      real :: C3_radMult = 0.0    ! axis-to-axis gap < C3_radMult * wireRadius
   contains
      procedure          :: fill_matrix_nec
      procedure, private :: Z_half_pair_nec
      procedure, private :: source_gauss_nec
      procedure, private :: source_gauss_bare
      procedure, private :: source_self_rtwk
      procedure, private :: source_self_etwk
      procedure, private :: source_pair_etwk
      procedure, private :: source_self_exact
      procedure, private :: source_pair_exact
      procedure, private :: etwk_core
      procedure, private :: exact_core
      procedure, private :: select_nQ
      procedure, private :: gap_within_radius
   end type NEC_ZFILL_TYPE

contains

!==============================================================================
!  fill_matrix_nec: plain Galerkin, same structure as zfill_m::fill_matrix.
!  Upper triangle only; matrix is symmetric (Galerkin), same as zfill_m.
!==============================================================================
   subroutine fill_matrix_nec(this, Basis, Segs, Bk, zMat, zGroundRefl)

      class(NEC_ZFILL_TYPE), intent(inout)        :: this
      type(BASIS2_TYPE),     intent(in)           :: Basis(:)
      type(SEGMENT_TYPE),    intent(in)           :: Segs(:)
      real,                  intent(in)           :: Bk
      complex, allocatable,  intent(out)          :: zMat(:,:)
      complex, optional,     intent(in)           :: zGroundRefl

      integer :: nB, m, n, p, q
      complex :: Zmn, Refl
      logical :: hasGround

      nB = size(Basis)
      allocate(zMat(nB, nB))
      zMat = zZERO

      hasGround = present(zGroundRefl)
      Refl      = zZERO
      if (hasGround) Refl = zGroundRefl

      write(*,'(a,i6,a,i0)') '  fill_matrix_nec: filling ', nB, &
         'x'//trim(adjustl(itoa(nB)))//' Z matrix, selfKernel=', this%selfKernel

      do m = 1, nB
         do n = m, nB

            Zmn = zZERO

            do p = 1, 2
               do q = 1, 2
                  Zmn = Zmn + this%Z_half_pair_nec( &
                           Basis(m)%half(p), Basis(n)%half(q), &
                           Basis(m)%radius,  Segs, Bk,         &
                           useImage=.false., Refl=zZERO )
               end do
            end do

            if (hasGround .and. abs(Refl) > ZERO) then
               do p = 1, 2
                  do q = 1, 2
                     Zmn = Zmn + this%Z_half_pair_nec( &
                              Basis(m)%half(p), Basis(n)%half(q), &
                              Basis(m)%radius,  Segs, Bk,         &
                              useImage=.true.,  Refl=Refl )
                  end do
               end do
            end if

            zMat(m, n) = Zmn
            !zMat(n, m) = Zmn    ! Galerkin symmetry -- uncomment for full matrix

         end do
      end do

   end subroutine fill_matrix_nec


!==============================================================================
!  Z_half_pair_nec: one (test half, source half) contribution. Full Galerkin
!  test quadrature (nQtest points), same as zfill_m. Only the source-side
!  kernel differs: RTWK offset for NEAR/FAR (source_gauss_nec), selectable
!  RTWK/ETWK for SELF (source_self_rtwk / source_self_etwk).
!==============================================================================
   function Z_half_pair_nec(this, Hp, Hq, wireRadius, Segs, Bk, useImage, Refl) result(Z)

      class(NEC_ZFILL_TYPE), intent(inout) :: this
      type(HALF_TYPE),       intent(in)    :: Hp
      type(HALF_TYPE),       intent(in)    :: Hq
      real,                  intent(in)    :: wireRadius
      type(SEGMENT_TYPE),    intent(in)    :: Segs(:)
      real,                  intent(in)    :: Bk
      logical,                intent(in)    :: useImage
      complex,                intent(in)    :: Refl
      complex                              :: Z

      type(SEGMENT_TYPE) :: Sp, Sq
      logical  :: isSelf, isNearTouching
      integer  :: ip, nQtest
      real     :: xTest, Lp, scalar_p, uDotu
      real     :: vTest(3)
      complex  :: Ivec, Iscl, A_pq, Phi_pq, jkEta, zSign

      Sp = Segs(Hp%iSeg)
      Sq = Segs(Hq%iSeg)

      isSelf = (Hp%iSeg == Hq%iSeg) .and. (.not. useImage)

      ! Of the non-self pairs, only route to the ETWK closed-form treatment
      ! (source_pair_etwk) when the field point's axial projection is
      ! actually likely to land at/near the source segment's own span --
      ! node-sharing or true surface proximity (isNearTouching below).
      ! Applying the singularity-subtracted ETWK formula further out
      ! overcorrects. Those pairs instead get graduated quadrature order
      ! from select_nQ via plain RTWK quadrature (source_gauss_nec) rather
      ! than the closed-form ETWK path.
      isNearTouching = (segments_share_node(Sp, Sq) .or. &
                         this%gap_within_radius(Sp, Sq, wireRadius)) .and. (.not. isSelf)

      jkEta = zIMAG * Bk * ETA0

      zSign = zONE
      if (useImage) zSign = Refl

      uDotu = dot_product(Sp%uHat, Sq%uHat)
      if (useImage) then
         uDotu = Sp%uHat(1)*Sq%uHat(1) &
               + Sp%uHat(2)*Sq%uHat(2) &
               - Sp%uHat(3)*Sq%uHat(3)
      end if

      Lp     = Sp%length
      if (isSelf .or. isNearTouching) then
         ! Self terms and node-sharing/surface-touching pairs keep the
         ! original fixed NQ_NEAR order -- they're handled by dedicated
         ! kernel formulas below (self_*/pair_*/source_gauss_bare), not by
         ! the graduated ladder, which targets moderately-close,
         ! non-touching pairs where a plain RTWK quadrature is used but the
         ! source segment can still subtend a large angle at the test point.
         nQtest = NQ_NEAR
      else
         ! Graduated quadrature order from the true minimum distance
         ! between the segments' axes -- see select_nQ.
         nQtest = this%select_nQ(Sp, Sq)
      end if

      A_pq   = zZERO
      Phi_pq = zZERO

      do ip = 1, nQtest

         xTest    = xi_n(ip, nQtest) * Lp
         vTest    = Sp%vNodes(:,1) + xTest * Sp%uHat
         scalar_p = scalar_fn(xTest, Lp, Hp%iEnd)

         if (isSelf) then
            select case (this%selfKernel)
            case (KERNEL_EXACT)
               call this%source_self_exact(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            case (KERNEL_ETWK)
               call this%source_self_etwk(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            case default
               call this%source_self_rtwk(xTest, wireRadius, Lp, Hq%iEnd, Bk, Ivec, Iscl)
            end select
         else if (isNearTouching .and. .not. useImage) then
            ! Node-sharing or true surface proximity. Kernel is configurable
            ! via nearKernel:
            !  KERNEL_EXACT/KERNEL_ETWK -> phi-averaged surface-current
            !    model (source_pair_exact/etwk), generalizing Burke's
            !    SELF-term formula to pair interactions -- Burke only
            !    validates this for the self term.
            !  KERNEL_RTWK -> simple filament + a^2-floor treatment, no
            !    phi-averaging (source_gauss_nec, forced to near-quadrature
            !    order).
            ! Image terms fall through to the plain RTWK path below -- the
            ! reflected geometry changes the projection algebra, not
            ! currently handled by the phi-averaged kernels.
            select case (this%nearKernel)
            case (KERNEL_EXACT)
               call this%source_pair_exact(vTest, Sq, wireRadius, Bk, Hq%iEnd, Ivec, Iscl)
            case (KERNEL_ETWK)
               call this%source_pair_etwk(vTest, Sq, wireRadius, Bk, Hq%iEnd, Ivec, Iscl)
            case (KERNEL_RTWK)
               call this%source_gauss_nec(vTest, Sq, wireRadius, Bk, Hq%iEnd, NQ_NEAR, useImage, Ivec, Iscl)
            case default   ! KERNEL_BARE
               call this%source_gauss_bare(vTest, Sq, Bk, Hq%iEnd, Ivec, Iscl)
            end select
         else
            call this%source_gauss_nec(vTest, Sq, wireRadius, Bk, Hq%iEnd, nQtest, useImage, Ivec, Iscl)
         end if

         A_pq   = A_pq   + w_n(ip, nQtest) * Lp * scalar_p * Ivec
         Phi_pq = Phi_pq + w_n(ip, nQtest) * Lp             * Iscl

      end do

      A_pq   = Hp%effSign * Hq%effSign * uDotu * A_pq
      Phi_pq = Hp%div     * Hq%div              * Phi_pq

      Z = zSign * jkEta * (A_pq - Phi_pq / (Bk * Bk))

   end function Z_half_pair_nec


!==============================================================================
!  source_gauss_nec: NEAR/FAR source integration. RTWK reduced-kernel radius
!  offset (Burke eq. 3, R0 = sqrt(rho^2+a^2+dz^2), which for a general 3-D
!  pair reduces to R = sqrt(|dr|^2 + a^2) since rho^2+dz^2 is exactly the
!  squared distance from the test point to the source axis) is applied only
!  for elevated-order (nQsrc > NQ_FAR) pairs -- see the Rsq computation
!  below. Genuine FAR pairs use bare R = |dr|.
!
!  nQsrc is passed in directly by the caller (nQtest for the graduated,
!  non-touching-pair branch; NQ_NEAR for the node-sharing/touching-pair
!  KERNEL_RTWK branch) rather than derived from a NEAR/FAR boolean here --
!  see select_nQ for how the graduated order is chosen.
!
!  ASSUMPTION: uses `wireRadius` for both test and source segment. If
!  SEGMENT_TYPE carries a per-segment radius, use Sq's own radius for the
!  source-side offset instead.
!==============================================================================
   subroutine source_gauss_nec(this, vTest, Sq, wireRadius, Bk, iEnd_q, nQsrc, useImage, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: wireRadius
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      integer,                intent(in)  :: nQsrc
      logical,                intent(in)  :: useImage
      complex,                intent(out) :: Ivec, Iscl

      integer :: iq
      real    :: xSrc, Lq, R, Rsq, scalar_q
      real    :: vSrc(3), vSrcImg(3), vR(3)
      complex :: Green

      Lq   = Sq%length
      Ivec = zZERO
      Iscl = zZERO

      do iq = 1, nQsrc

         xSrc = xi_n(iq, nQsrc) * Lq
         vSrc = Sq%vNodes(:,1) + xSrc * Sq%uHat

         if (useImage) then
            vSrcImg    = vSrc
            vSrcImg(3) = -vSrc(3)
            vR = vTest - vSrcImg
         else
            vR = vTest - vSrc
         end if

         ! RTWK offset (Burke eq.3's a^2 term) applied only for elevated-order
         ! (nQsrc > NQ_FAR) pairs, not unconditionally: for two closely-spaced
         ! parallel wires, input reactance is governed by self-inductance
         ! MINUS mutual-inductance cancellation between the wires; softening
         ! 1/R (via +a^2) on cross-wire FAR-classified pairs weakens that
         ! mutual coupling and inflates net reactance. Genuine FAR pairs use
         ! bare-R; the offset applies only where the elevated quadrature
         ! order signals a quadrature-resolution concern.
         if (nQsrc > NQ_FAR) then
            Rsq = dot_product(vR, vR) + wireRadius * wireRadius
         else
            Rsq = dot_product(vR, vR)
         end if
         R   = sqrt(Rsq)
         if (R < 1.0e-12) R = 1.0e-12

         Green = w_n(iq, nQsrc) * Lq * exp(-zIMAG*Bk*R) / (FOURPI * R)

         scalar_q = scalar_fn(xSrc, Lq, iEnd_q)

         Ivec = Ivec + scalar_q * Green
         Iscl = Iscl +            Green

      end do

   end subroutine source_gauss_nec


!==============================================================================
!  source_gauss_bare: exact transcription of original zfill_m::source_gauss.
!  Bare R = |dr|, no offset of any kind -- not a^2, not phi-averaging.
!  NQ_NEAR quadrature order always (caller only invokes this when
!  isNearTouching).
!==============================================================================
   subroutine source_gauss_bare(this, vTest, Sq, Bk, iEnd_q, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      complex,                intent(out) :: Ivec, Iscl

      integer :: iq
      real    :: xSrc, Lq, R, scalar_q
      real    :: vSrc(3), vR(3)
      complex :: Green

      Lq   = Sq%length
      Ivec = zZERO
      Iscl = zZERO

      do iq = 1, NQ_NEAR

         xSrc = xi_n(iq, NQ_NEAR) * Lq
         vSrc = Sq%vNodes(:,1) + xSrc * Sq%uHat

         vR = vTest - vSrc
         R  = norm2(vR)
         if (R < 1.0e-12) R = 1.0e-12

         Green = w_n(iq, NQ_NEAR) * Lq * exp(-zIMAG*Bk*R) / (FOURPI * R)

         scalar_q = scalar_fn(xSrc, Lq, iEnd_q)

         Ivec = Ivec + scalar_q * Green
         Iscl = Iscl +            Green

      end do

   end subroutine source_gauss_bare


!==============================================================================
!  source_self_rtwk: RTWK self term, via Gibson's closed form rather than
!  direct quadrature of e^{-jkR0}/R0. For a=x << L (typical thin wire, L/a
!  often in the hundreds), 1/R0 is a ridge only about `a` wide sitting
!  inside a domain of length L -- a fixed-order Gauss-Legendre rule over the
!  whole segment cannot resolve it without a singularity-subtraction scheme,
!  at which point it stops being a distinct RTWK baseline from ETWK. This is
!  mathematically the same integral Gibson's closed form evaluates (R0 =
!  sqrt(a^2+x^2) is exactly Burke's RTWK R0 at rho=0), so it's used directly.
!
!  Reference: Gibson, "The Method of Moments in Electromagnetics", 2nd ed.,
!  Sec. 4.5.2, Eqs. 4.83-4.86 -- reproduced from zfill_m::source_self_analytical.
!==============================================================================
   subroutine source_self_rtwk(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x, a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      real    :: R0, RL, arglog
      complex :: S1_asc, S1_desc, S2

      R0     = sqrt(a*a + x*x)
      RL     = sqrt(a*a + (x - L)*(x - L))

      arglog = log( (x + R0) / max(abs(x - L + RL), 1.0e-30) )

      S1_asc  =  (RL/L - R0/L + (x/L)*arglog) - zIMAG*(Bk*L/2.0)   ! iEnd_q=2
      S1_desc = -(RL/L - R0/L + (x/L)*arglog) - zIMAG*(Bk*L/2.0) + arglog  ! iEnd_q=1

      S2 = (ONE/L) * (arglog - zIMAG*(Bk*L))

      S1_asc  = S1_asc  / FOURPI
      S1_desc = S1_desc / FOURPI
      S2      = S2 * L  / FOURPI

      Ivec = merge(S1_asc, S1_desc, iEnd_q == 2)
      Iscl = S2

   end subroutine source_self_rtwk


!==============================================================================
!  source_self_etwk: ETWK self term, Burke eq. 2, 4, 5, evaluated at the wire
!  SURFACE (rho=a), matching Burke's own ETWK self-term convention ("The
!  ETWK was evaluated at the wire surface, K1(a,0)").
!
!  K1(rho,z) = 2*pi * INT_{-L/2}^{L/2} (e^{-jkR0}-1)/R0 dz'      [regular]
!            + INT_{-pi}^{pi} Kz(rho,z,phi) dphi                 [singular, closed-form-in-z']
!
!  where (eq. 5, singularity extracted):
!    Kz(rho,z,phi) = -log(a^2+rho^2-2*a*rho*cos(phi))
!                   + log[ (-z1+sqrt(a^2+z1^2+rho^2-2*a*rho*cos(phi)))
!                        * ( z2+sqrt(a^2+z2^2+rho^2-2*a*rho*cos(phi))) ]
!    z1 = -L/2 - z,  z2 = L/2 - z    (z measured from segment center)
!
!  and the singular piece integrates in closed form:
!    INT_{-pi}^{pi} log(a^2+rho^2-2*a*rho*cos(phi)) dphi = 4*pi*log(max(a,rho))
!
!  Both formulas are Burke's, reproduced directly (relabeled to this
!  module's x-from-left-node convention: z = x - L/2).
!
!  WEIGHTED (Ivec) EXTENSION -- NOT FROM THE PAPER:
!  Burke's K1 is for constant source density. For the rooftop scalar_q(z')
!  ramp, standard singularity subtraction is used: the closed-form log
!  (singular) term is weighted by scalar_q evaluated at the test point
!  (since the z' dependence in that term has already been integrated out
!  analytically), while the regular (e^{-jkR0}-1)/R0 term is weighted
!  pointwise by scalar_q(z') under the z' quadrature, as usual.
!==============================================================================
   subroutine source_self_etwk(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x       ! test position, 0..L from left node
      real,                   intent(in)  :: a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      ! Burke's ETWK self-term convention: evaluate at the wire surface
      ! (rho=a), not the axis -- see header note in etwk_core.
      call this%etwk_core(a, x, a, L, iEnd_q, Bk, Ivec, Iscl)

   end subroutine source_self_etwk


!==============================================================================
!  source_pair_etwk: ETWK applied to a NEAR (different-segment, node-sharing)
!  pair. Projects the test point onto the source segment Sq's axis line to
!  get the geometric (rho, s) that Burke's eq. 1-5 need -- this is the
!  generalization discussed in the module header: the closed-form
!  log-singularity extraction is valid for ANY straight source segment and
!  ANY field point, not just the self-term case.
!
!  Geometry: for source axis point at parameter s in [0,Lq] from Sq's left
!  node A, position = A + s*uHat. Let d0 = vTest - A. Then:
!    s_test = dot(d0, uHat)              -- projection of vTest onto the axis
!    dperp  = d0 - s_test*uHat           -- perpendicular component
!    rho    = |dperp|                    -- true perpendicular distance
!  and |vTest - (A+s*uHat)|^2 = rho^2 + (s_test-s)^2 for any s, which is
!  exactly Burke's R0(rho,z-z') form with z = s_test (measured from A).
!  s_test can legitimately fall outside [0,Lq] (test point projects beyond
!  the source segment's own extent) -- the closed form is valid there too.
!==============================================================================
   subroutine source_pair_etwk(this, vTest, Sq, wireRadius, Bk, iEnd_q, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: wireRadius   ! source wire radius, a
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      complex,                intent(out) :: Ivec, Iscl

      real :: d0(3), dperp(3), s_test, rho, Lq

      Lq = Sq%length
      d0 = vTest - Sq%vNodes(:,1)
      s_test = dot_product(d0, Sq%uHat)
      dperp  = d0 - s_test * Sq%uHat
      rho    = norm2(dperp)

      call this%etwk_core(rho, s_test, wireRadius, Lq, iEnd_q, Bk, Ivec, Iscl)

   end subroutine source_pair_etwk


!==============================================================================
!  etwk_core: shared ETWK math (Burke eq. 2, 4, 5), factored out of
!  source_self_etwk / source_pair_etwk. rho and x (field-point axial
!  coordinate, measured from the source segment's LEFT node, 0..L range but
!  not restricted to it) are supplied by the caller; everything else is the
!  same closed-form/quadrature split described in the module header.
!
!  WEIGHTED (Ivec) EXTENSION -- NOT FROM THE PAPER (see module header):
!  the closed-form singular term is weighted by scalar_q evaluated at x --
!  i.e. at the source segment's own coordinate nearest the field point's
!  axial projection, which is where the near-singular behavior is
!  concentrated.
!==============================================================================
   subroutine etwk_core(this, rho, x, a, L, iEnd_q, Bk, Ivec, Iscl)

      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: rho     ! perpendicular distance, field pt to source axis
      real,                   intent(in)  :: x       ! field pt axial coord, 0..L from left node (source frame)
      real,                   intent(in)  :: a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      integer :: iz, iphi
      real    :: zp, z, z1, z2, R0, scalar_q, scalar_test
      real    :: phi, cphi, singPart, regPhiIntegrand, phiIntegral, epsPhi
      complex :: Green0, term1_vec, term1_scl

      z  = x - L/2.0          ! recenter to Burke's [-L/2, L/2] convention
      z1 = -L/2.0 - z
      z2 =  L/2.0 - z

      ! --- Regular term: 2*pi * INT (e^{-jkR0}-1)/R0 dz', both unweighted
      !     (Iscl) and ramp-weighted (Ivec). R0 per eq.2 = sqrt(rho^2+a^2+(z-z')^2)
      !     (R evaluated at phi=pi/2, per Burke's definition below eq.2).
      term1_vec = zZERO
      term1_scl = zZERO
      do iz = 1, NQ_NEAR
         zp = xi_n(iz, NQ_NEAR) * L                       ! [0,L] from left node
         R0 = sqrt(rho*rho + a*a + (x - zp)*(x - zp))
         if (R0 < 1.0e-12) R0 = 1.0e-12

         Green0   = w_n(iz, NQ_NEAR) * L * (exp(-zIMAG*Bk*R0) - ONE) / R0
         scalar_q = scalar_fn(zp, L, iEnd_q)

         term1_vec = term1_vec + scalar_q * Green0
         term1_scl = term1_scl +            Green0
      end do
      term1_vec = 2.0 * PI * term1_vec
      term1_scl = 2.0 * PI * term1_scl

      ! --- Singular term: INT_{-pi}^{pi} Kz(rho,z,phi) dphi via eq. 5,
      !     closed-form log-singularity extraction + Gauss-Legendre over phi
      singPart = 4.0 * PI * log(max(a, rho))

      phiIntegral = 0.0
      do iphi = 1, NQ_PHI
         phi  = -PI + 2.0*PI * xi_n(iphi, NQ_PHI)          ! map [0,1] -> [-pi,pi]
         cphi = cos(phi)

         ! eps = a^2+rho^2-2*a*rho*cos(phi) >= 0 always. The two factors
         ! below are (-z1)+sqrt(z1^2+eps) and z2+sqrt(z2^2+eps) -- each is
         ! mathematically >=0, but computed as X+sqrt(X^2+eps) this suffers
         ! catastrophic cancellation whenever X<0 and |X| is large relative
         ! to eps (i.e. the field-point axial projection lands well outside
         ! [0,L] -- expected for isNearTouching pairs close by true axis
         ! distance but far apart along the axis). Use stable_xpsqrt below
         ! rather than the direct sum.
         epsPhi = a*a + rho*rho - 2.0*a*rho*cphi

         regPhiIntegrand = log( max( stable_xpsqrt(-z1, epsPhi) * stable_xpsqrt(z2, epsPhi), 1.0e-30 ) )

         phiIntegral = phiIntegral + w_n(iphi, NQ_PHI) * 2.0*PI * regPhiIntegrand
      end do

      ! Iscl: K1 normalized to match zfill_m's G=exp(-jkR)/(4*pi*R) filament
      ! convention. NOTE: term1_scl is already complex (carries e^{-jkR0}
      ! phase from Green0) -- do NOT wrap in cmplx(...,0.0) here, that
      ! silently drops its imaginary part. (-singPart+phiIntegral) is real
      ! and promotes fine under ordinary complex+real addition.
      !
      ! NORMALIZATION: Burke's K0 (eq.3) = 2*pi * INT e^{-jkR0}/R0 dz'.
      ! source_self_rtwk computes the plain filament integral
      ! INT e^{-jkR0}/R0 dz' directly (no 2*pi), normalized by /(4*pi) --
      ! i.e. it computes K0/(8*pi^2). K1 is built on the same K convention
      ! as K0 (both approximate the same Burke eq.1 double integral), so it
      ! needs the same divisor, K1/(8*pi^2), not K1/(4*pi).
      Iscl = (term1_scl + (-singPart + phiIntegral)) / (FOURPI * 2.0*PI)

      ! Ivec: singularity-subtraction weighting -- see header note above.
      ! Same /(8*pi^2) normalization as Iscl -- both pieces of K1
      ! (term1_vec and the closed-form part) are on Burke's K-convention.
      scalar_test = scalar_fn(x, L, iEnd_q)
      Ivec = (term1_vec + scalar_test * (-singPart + phiIntegral)) / (FOURPI * 2.0*PI)

   end subroutine etwk_core


!==============================================================================
!  source_self_exact / source_pair_exact / exact_core: KERNEL_EXACT path.
!
!  No closed form, no approximation of any kind -- direct double Gauss-
!  Legendre quadrature (NQ_EXACT x NQ_EXACT = 32x32) of the true kernel
!
!      exp(-jkR)/R,   R = sqrt(rho^2 + a^2 + (x-z')^2 - 2*a*rho*cos(phi))
!
!  (Burke eq.1's integrand, before any RTWK/ETWK approximation is applied to
!  it). This exists because ETWK's "regular" term approximates the true
!  kernel's phi-dependence by evaluating it once at phi=pi/2 and multiplying
!  by 2*pi, which underestimates the true kernel by up to ~17% when rho is
!  comparable to a. R is never actually zero here (it's bounded below by a),
!  so the integrand is smooth, not singular -- ordinary Gauss-Legendre
!  converges fast on it; NQ_EXACT=32 is generous headroom, not a bare
!  minimum. The ramp weight scalar_q(z') is applied directly inside the z'
!  quadrature -- no singularity-subtraction approximation needed at all for
!  the weighted (Ivec) term, unlike etwk_core.
!
!  Normalization: same /(8*pi^2) divisor as etwk_core -- RTWK, ETWK, and
!  EXACT all approximate (EXACT: exactly, to quadrature precision) the same
!  underlying Burke eq.1 double integral, so all three need the same overall
!  normalization to be comparable / substitutable in Z_half_pair_nec.
!==============================================================================
   subroutine source_self_exact(this, x, a, L, iEnd_q, Bk, Ivec, Iscl)
      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: x, a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      ! Self term evaluated at the wire surface (rho=a), same convention as
      ! source_self_etwk / Burke's own ETWK self-term choice.
      call this%exact_core(a, x, a, L, iEnd_q, Bk, Ivec, Iscl)
   end subroutine source_self_exact


   subroutine source_pair_exact(this, vTest, Sq, wireRadius, Bk, iEnd_q, Ivec, Iscl)
      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: vTest(3)
      type(SEGMENT_TYPE),     intent(in)  :: Sq
      real,                   intent(in)  :: wireRadius
      real,                   intent(in)  :: Bk
      integer,                intent(in)  :: iEnd_q
      complex,                intent(out) :: Ivec, Iscl

      real :: d0(3), dperp(3), s_test, rho, Lq

      ! Same projection geometry as source_pair_etwk.
      Lq = Sq%length
      d0 = vTest - Sq%vNodes(:,1)
      s_test = dot_product(d0, Sq%uHat)
      dperp  = d0 - s_test * Sq%uHat
      rho    = norm2(dperp)

      call this%exact_core(rho, s_test, wireRadius, Lq, iEnd_q, Bk, Ivec, Iscl)
   end subroutine source_pair_exact


   subroutine exact_core(this, rho, x, a, L, iEnd_q, Bk, Ivec, Iscl)
      class(NEC_ZFILL_TYPE), intent(in)  :: this
      real,                   intent(in)  :: rho     ! perpendicular distance, field pt to source axis
      real,                   intent(in)  :: x       ! field pt axial coord, 0..L from left node (source frame)
      real,                   intent(in)  :: a, L
      integer,                intent(in)  :: iEnd_q
      real,                   intent(in)  :: Bk
      complex,                intent(out) :: Ivec, Iscl

      integer :: iz, iphi
      real    :: zp, phi, cphi, R, scalar_q, wz
      complex :: kernel, sumScl, sumVec

      sumScl = zZERO
      sumVec = zZERO

      do iz = 1, NQ_EXACT
         zp = xi_n(iz, NQ_EXACT) * L                       ! [0,L] from left node
         wz = w_n(iz, NQ_EXACT) * L
         scalar_q = scalar_fn(zp, L, iEnd_q)

         do iphi = 1, NQ_EXACT
            phi  = -PI + 2.0*PI * xi_n(iphi, NQ_EXACT)
            cphi = cos(phi)

            R = sqrt(rho*rho + a*a + (x-zp)*(x-zp) - 2.0*a*rho*cphi)
            if (R < 1.0e-12) R = 1.0e-12   ! guard only; R>=a-rho... never
                                           ! actually reached in practice

            kernel = wz * w_n(iphi, NQ_EXACT)*2.0*PI * exp(-zIMAG*Bk*R) / R

            sumScl = sumScl +            kernel
            sumVec = sumVec + scalar_q * kernel
         end do
      end do

      Iscl = sumScl / (FOURPI * 2.0*PI)
      Ivec = sumVec / (FOURPI * 2.0*PI)

   end subroutine exact_core


!==============================================================================
!  Helpers
!==============================================================================

   pure real function scalar_fn(x, L, iEnd)
      real,    intent(in) :: x, L
      integer, intent(in) :: iEnd
      if (iEnd == 2) then
         scalar_fn = x / L
      else
         scalar_fn = (L - x) / L
      end if
   end function scalar_fn

!==============================================================================
!  select_nQ: graduated quadrature-order selection for non-self,
!  non-touching pairs, based on the true minimum distance between the two
!  segments' axes (finite segments, not infinite lines -- seg_seg_distance),
!  not centroid distance -- centroid separation is fooled by long, closely-
!  spaced antiparallel runs (e.g. a tightly-spaced parallel-wire
!  transmission line), where two facing segments' centroids sit a full
!  segment-length apart even though their nearest points are only a few
!  wire-diameters away.
!
!  ratio = Lmax / gap, where Lmax = max(Sp%length, Sq%length) and gap is the
!  true axis-to-axis segment distance. The larger the ratio, the more the
!  source segment subtends at the test point relative to how close it is,
!  so the faster 1/R and e^{-jkR} vary across the quadrature domain, and the
!  higher the order needed to resolve them.
!
!  Pure geometry -- no wireRadius or wavelength dependence. A fixed physical
!  gap (e.g. a 2cm-spaced TL) needs the same quadrature resolution
!  regardless of frequency, but NBASISPERLAMBDA-driven meshing is
!  wavelength-relative, so a wavelength-relative quadrature criterion would
!  compound rather than compensate for that mismatch at the low-frequency
!  end of a sweep.
!
!  Segment endpoints are computed as vNodes(:,1) + length*uHat rather than
!  assuming a second vNodes column exists -- matches how the rest of this
!  module (and zfill_m) reaches a segment's far end.
!==============================================================================
   pure integer function select_nQ(this, Sp, Sq)
      class(NEC_ZFILL_TYPE), intent(in) :: this
      type(SEGMENT_TYPE),    intent(in) :: Sp, Sq

      real, parameter :: GAP_FLOOR = 1.0e-6
      real :: P1(3), Q1(3), P2(3), Q2(3), dGap, Lmax, ratio

      P1 = Sp%vNodes(:,1)
      Q1 = Sp%vNodes(:,1) + Sp%length*Sp%uHat
      P2 = Sq%vNodes(:,1)
      Q2 = Sq%vNodes(:,1) + Sq%length*Sq%uHat
      dGap = seg_seg_distance(P1, Q1, P2, Q2)

      Lmax  = max(Sp%length, Sq%length)
      ratio = Lmax / max(dGap, GAP_FLOOR)

      if (ratio < 2.0) then
         select_nQ = NQ_FAR
      else if (ratio < 25.0) then
         select_nQ = NQ_NEAR
      else if (ratio < 60.0) then
         select_nQ = NQ_64
      else
         select_nQ = NQ_128
      end if

   end function select_nQ


!==============================================================================
!  gap_within_radius: true surface-proximity check (axis-to-axis segment
!  distance vs. C3_radMult*wireRadius), used by Z_half_pair_nec to decide
!  ETWK routing (isNearTouching).
!==============================================================================
   pure logical function gap_within_radius(this, Sp, Sq, wireRadius)
      class(NEC_ZFILL_TYPE), intent(in) :: this
      type(SEGMENT_TYPE),    intent(in) :: Sp, Sq
      real,                   intent(in) :: wireRadius

      real :: P1(3), Q1(3), P2(3), Q2(3), dAxis

      P1 = Sp%vNodes(:,1)
      Q1 = Sp%vNodes(:,1) + Sp%length*Sp%uHat
      P2 = Sq%vNodes(:,1)
      Q2 = Sq%vNodes(:,1) + Sq%length*Sq%uHat
      dAxis = seg_seg_distance(P1, Q1, P2, Q2)

      gap_within_radius = (dAxis < this%C3_radMult*wireRadius)

   end function gap_within_radius


!==============================================================================
!  seg_seg_distance: minimum distance between two finite 3-D line segments
!  (P1-Q1 and P2-Q2). Standard closest-point-between-segments algorithm
!  (e.g. Ericson, "Real-Time Collision Detection", sec. 5.1.9), NOT the
!  infinite-line distance -- using the infinite line would understate the
!  gap for segments that pass near each other's extended axis without
!  actually being close (e.g. two collinear, non-overlapping segments at
!  the far ends of a transmission line).
!==============================================================================
   pure real function seg_seg_distance(P1, Q1, P2, Q2)
      real, intent(in) :: P1(3), Q1(3), P2(3), Q2(3)

      real, parameter :: EPS = 1.0e-12
      real :: d1(3), d2(3), r(3), a, e, f, c, b, denom, s, t
      real :: c1(3), c2(3)

      d1 = Q1 - P1
      d2 = Q2 - P2
      r  = P1 - P2
      a  = dot_product(d1, d1)
      e  = dot_product(d2, d2)
      f  = dot_product(d2, r)

      if (a <= EPS .and. e <= EPS) then
         seg_seg_distance = norm2(r)
         return
      end if

      if (a <= EPS) then
         s = 0.0
         t = clamp01(f / e)
      else
         c = dot_product(d1, r)
         if (e <= EPS) then
            t = 0.0
            s = clamp01(-c / a)
         else
            b = dot_product(d1, d2)
            denom = a*e - b*b
            if (abs(denom) > EPS) then
               s = clamp01((b*f - c*e) / denom)
            else
               s = 0.0
            end if
            t = (b*s + f) / e
            if (t < 0.0) then
               t = 0.0
               s = clamp01(-c / a)
            else if (t > 1.0) then
               t = 1.0
               s = clamp01((b - c) / a)
            end if
         end if
      end if

      c1 = P1 + d1*s
      c2 = P2 + d2*t
      seg_seg_distance = norm2(c1 - c2)

   end function seg_seg_distance

   pure real function clamp01(v)
      real, intent(in) :: v
      clamp01 = max(0.0, min(1.0, v))
   end function clamp01

!==============================================================================
!  stable_xpsqrt: numerically stable X + sqrt(X^2+eps), eps>=0.
!  Mathematically always >=0 (sqrt(X^2+eps) >= |X|). Direct evaluation
!  suffers catastrophic cancellation when X<0 and |X| >> sqrt(eps) -- use
!  the conjugate form eps/(sqrt(X^2+eps)-X) there instead, whose
!  denominator is a sum of two non-negative terms (sqrt(...) and -X, both
!  >=0 when X<0) and so is well-conditioned.
!==============================================================================
   pure real function stable_xpsqrt(X, eps)
      real, intent(in) :: X, eps
      real :: s
      s = sqrt(X*X + eps)
      if (X >= 0.0) then
         stable_xpsqrt = X + s
      else
         stable_xpsqrt = eps / (s - X)
      end if
   end function stable_xpsqrt

   pure logical function segments_share_node(Sp, Sq)
      type(SEGMENT_TYPE), intent(in) :: Sp, Sq
      segments_share_node = &
         (Sp%iLeftNode  == Sq%iLeftNode)  .or. &
         (Sp%iLeftNode  == Sq%iRightNode) .or. &
         (Sp%iRightNode == Sq%iLeftNode)  .or. &
         (Sp%iRightNode == Sq%iRightNode)
   end function segments_share_node

   pure real function xi_n(i, nQ)
      integer, intent(in) :: i, nQ
      select case (nQ)
      case (NQ_FAR)
         xi_n = XI4(i)
      case (NQ_NEAR)   ! == NQ_PHI (both 16) by construction
         xi_n = XI16(i)
      case (NQ_64)
         xi_n = XI64(i)
      case (NQ_128)
         xi_n = XI128(i)
      case (NQ_EXACT)
         xi_n = XI32(i)
      case default
         xi_n = XI16(i)   ! should not happen; fall back rather than crash
      end select
   end function xi_n

   pure real function w_n(i, nQ)
      integer, intent(in) :: i, nQ
      select case (nQ)
      case (NQ_FAR)
         w_n = W4(i)
      case (NQ_NEAR)
         w_n = W16(i)
      case (NQ_64)
         w_n = W64(i)
      case (NQ_128)
         w_n = W128(i)
      case (NQ_EXACT)
         w_n = W32(i)
      case default
         w_n = W16(i)
      end select
   end function w_n

   pure function itoa(n) result(s)
      integer, intent(in) :: n
      character(len=12) :: s
      write(s,'(i0)') n
      s = adjustl(s)
   end function itoa

end module zfill_nec_m
