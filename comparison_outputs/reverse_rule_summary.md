# Complete Case Comparison Summary

Source workbook: `complete_case_chemical_lists_ICE105_Skin209.xlsx`

## Direct Comparison

| Dataset | Colleague count | Current count | Common | Colleague only | Current only |
| --- | ---: | ---: | ---: | ---: | ---: |
| ICE | 105 | 64 | 42 | 63 | 22 |
| SkinSensDB | 209 | 208 | 208 | 1 | 0 |

## SkinSensDB

The current 208 SkinSensDB complete cases are all present in the colleague sheet after normalizing Excel-converted CAS dates.

The one extra colleague row is `2-(4-Amino-2nitro-phenylamino)-ethanol`. Current output has KE1, KE3, and LLNA, but missing KE2. The colleague sheet assigns `KE2_call=0`, so their rule likely treated missing KE2 as inactive/negative.

## ICE

All 63 colleague-only ICE rows are present in the current full ICE output, have `LLNA_EC3`, and are missing `LLNA_call`. This suggests the colleague derived LLNA from EC3 when LLNA call was absent.

The colleague ICE calls do not fully match the current OR rule for KE2/KE3:

- Current OR rule mismatches against the colleague sheet: 4
- Consensus rule mismatches against the colleague sheet: 0

The consensus rule is: if any available component assay is `Inactive`, the composite KE call is `0`; otherwise, if at least one available component assay is `Active`, the composite KE call is `1`. This matches the colleague ICE calls better than the current OR rule.

The broad inferred rule:

`KE1_call + KE2_call + KE3_call + (LLNA_call OR LLNA_EC3)`

produces 144 ICE candidates and contains all 105 colleague ICE rows. It also produces 39 extra rows not in the colleague workbook, so there is likely another undocumented filter or extraction difference.
