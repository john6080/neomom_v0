# References — Near-Pair Thin-Wire Impedance Integral Accuracy

Context: `zfill_m.f90::source_gauss` currently evaluates NEAR (non-self,
node-sharing) segment-pair impedance integrals with a fixed 16-point
Gauss-Legendre rule and no singularity treatment. These references are
candidate starting points for a proper near-singular/near-hypersingular
treatment, in the same spirit as the Gibson closed-form self-term already
in use.

## Near-singular / near-hypersingular integral evaluation

- P. W. Fink, D. R. Wilton, M. A. Khayat, "Simple and efficient numerical
  evaluation of near-hypersingular integrals," *IEEE Antennas and Wireless
  Propagation Letters*, vol. 7, pp. 469–472, 2008.

- D. R. Wilton, S. M. Rao, A. W. Glisson, D. H. Schaubert, O. M. Al-Bundak,
  C. M. Butler, "Potential integrals for uniform and linear source
  distribution on polygonal and polyhedral domains," *IEEE Transactions on
  Antennas and Propagation*, vol. 32, no. 3, pp. 276–281, March 1984.

## Thin-wire impedance integral precision (Krneta / Kolundžija)

- A. Krneta et al., "Singularity cancellation and extraction techniques
  for precise evaluation of impedance integrals in thin-wire analysis,"
  IEEE APS/URSI Symposium, 2016. IEEE Xplore document 7481384.

- A. J. Krneta and B. M. Kolundžija, "Evaluation of Potential and
  Impedance Integrals in Analysis of Axially Symmetric Metallic
  Structures to Prescribed Accuracy Up To Machine Precision," *IEEE
  Transactions on Antennas and Propagation*, vol. 65, no. 5,
  pp. 2526–2539, May 2017.

- A. J. Krneta and B. M. Kolundžija, "Using ultra-high expansion orders
  of max-ortho basis functions for analysis of axially symmetric metallic
  antennas," *IEEE Transactions on Antennas and Propagation*, vol. 66,
  no. 7, pp. 3696–3699, July 2018.

## Related background (NEC thin-wire kernel / bend handling)

- G. J. Burke, A. J. Poggio, "Numerical Electromagnetics Code (NEC) —
  Method of Moments, Part I: Program Description — Theory," Technical
  Document 116, Naval Ocean Systems Center, January 1981.

- T. K. Sarkar, "The Method of Moments Applied to Antennas" (tutorial
  notes) — thin-wire kernel accuracy near junctions and wire ends.

Note: citations above were compiled from web search results and
reference lists in other papers, not from reading the full source
documents directly. Verify details (page numbers, exact title wording)
against the original publication before citing formally.
