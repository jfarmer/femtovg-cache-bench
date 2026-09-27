# Application context

These synthetic experiments originated in an Alustin application performance investigation. A separate ten-launch comparison measured startup medians of 174.77 ms for the #343 policy, 174.35 ms for flush-aware 64, and 171.89 ms for strict LRU 128. Each created 32 pipelines initially and two during search: the working set fit all three caches. The timing differences were within launch variation and did not establish an application startup improvement.

That application experiment is not reproduced by this standalone harness. Its application-specific source and logs are not bundled here. Use the included synthetic raw data and methodology to support claims about the workloads this repository can reproduce.
