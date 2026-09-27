# Historical sanity check

This compares work with the prior standalone rerun. It does not provide the primary performance estimates. The primary campaign uses a newer FemtoVG base, including expanded WGSL blend support, and the exact current proposal. It also uses explicit full-trace priming. Timing changes cannot be attributed to a single cause from this comparison.

- direct: 240 repeated process profiles match every creation/residency count; 0 processes belong to new cases. Across common cases, completed-time medians change by -0.3% to +30.1%.
- policies: 240 repeated process profiles match every creation/residency count; 80 processes belong to new cases. Across common cases, completed-time medians change by -11.3% to +20.7%.
- All 7,200 CPU simulation records match exactly.

The underlying work reproduces. Absolute timing differences remain; the primary report uses only the new campaign for policy comparisons.
