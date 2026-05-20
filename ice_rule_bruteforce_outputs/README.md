# ICE Rule Brute-Force Notes

This output is not trying to prove that any historical count, such as 105, is correct.
It is meant to show how sensitive the final ICE dataset is to rule interpretation.

Main rule dimensions:

- KE2/KE3 aggregation:
  - `or_positive`: a composite KE is positive if any component assay is Active.
  - `consensus_negative`: a composite KE is negative if any component assay is Inactive.
- Conflict handling:
  - `exclude_conflicts = True` removes chemicals where component assays disagree.
- Complete-case mode:
  - `call_based`: requires KE1 call, KE2 call, KE3 call, and selected LLNA call.
  - `metric_source_based`: requires KE1 metric, at least one KE2 source, at least one KE3 source, and LLNA EC3.
- LLNA priority:
  - controls which LLNA source is used first when several are available.

Recommended Samantha rule from the latest email:

- `ke2_mode = or_positive`
- `ke3_mode = or_positive`
- `exclude_conflicts = True`
- `complete_mode = call_based`
- `llna_priority = call > epa > ec3`

That corresponds to the same logic as `ICE_COMPLETE_CASE_OPTION = 4` in `ice_process.py`.
