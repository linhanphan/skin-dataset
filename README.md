# Skin Sensitization Dataset Processing

This repository processes ICE and SkinSensDB raw files into assay-level chemical tables. The rules below are written as implementation specs: each rule states what counts as present, how calls are assigned, and what should remain missing.

## Files

- `ice_process.py`: reads `RAW_ICE_skin_sensitization.xlsx` and writes ICE outputs. The selected complete-case rule is controlled by `ICE_COMPLETE_CASE_OPTION` near the top of the script. Output filenames include `option_1`, `option_2`, `option_3`, or `option_4`; legacy alias files are also written for downstream scripts.
- `skinsens.py`: reads `RAW_SKINSENS_DB_complete.xls` and writes `Skin_endpoint_presence_from_raw.csv` plus `Skin_complete_cases_from_raw.csv`.
- `synthetic.py`: reads the processed CSV files and writes `analysis_outputs.xlsx` and `analysis_quick_view.csv`.
- `compare_colleague_complete_cases.py`: compares current complete-case outputs with `complete_case_chemical_lists_ICE105_Skin209.xlsx` and writes diagnostics under `comparison_outputs/`.
- `brute_force_ice_rules.py`: enumerates plausible ICE rule combinations for KE2/KE3 aggregation, LLNA source priority, conflict exclusion, and complete-case definition. It writes summaries under `ice_rule_bruteforce_outputs/`.

## Rule Writing Guidelines

When changing or adding a rule, write it so a person and a coding agent can both implement it without guessing:

- State the input columns or endpoints.
- State what counts as present and what counts as missing.
- State how numeric text values such as `>2000`, `<179`, and `ND` should be parsed.
- State positive, negative, and missing outcomes separately.
- State how to handle disagreements between component assays.
- State the priority order when multiple evidence sources can produce the same final call.
- State whether missing evidence should remain missing or be treated as negative. Prefer keeping missing as missing unless the scientific rule explicitly says otherwise.

## SkinSensDB Rules

### Censored Numeric Values

Raw SkinSensDB values can contain censored numeric text such as `>2000`, `<179`, `>922.33`, or `ND`.

- Do not edit the raw file by hand.
- The code parses censored values before applying threshold rules.
- Exact mappings can be added to `CENSORED_VALUE_MAP` near the top of `skinsens.py`, for example `">2000": 2001` or `"<192": 191`.
- If a censored value is not listed in `CENSORED_VALUE_MAP`, the fallback rule is used: `>x` maps to `x + 1`, and `<x` maps to `x - 1`.
- `NaN`, `ND`, `NC`, `IDR`, blank cells, and other non-numeric text remain missing.
- The original raw file remains unchanged.

### KE1

- Inputs: `DPRA_Cys` and `DPRA_Lys`.
- `KE1_metric` is the mean of available `DPRA_Cys` and `DPRA_Lys` values.
- `KE1_call = 1` when `KE1_metric >= 6.38`.
- `KE1_call = 0` when `KE1_metric < 6.38`.
- `KE1_call` is missing when `KE1_metric` is missing.

### KE2

- Input: `KeratinoSens_LuSens_EC15`.
- `KE2_metric` is the parsed numeric value from `KeratinoSens_LuSens_EC15`.
- `KE2_call = 1` when `KE2_metric <= 1000`.
- `KE2_call = 0` when `KE2_metric > 1000`.
- `KE2_call` is missing when `KE2_metric` is missing.

### KE3

- Inputs: `h-CLAT_U-SENS_EC150` and `h-CLAT_EC200`.
- `KE3_metric` is the minimum available value across those two inputs.
- `KE3_call = 1` when `h-CLAT_U-SENS_EC150 <= 150` or `h-CLAT_EC200 <= 200`.
- `KE3_call = 0` when at least one KE3 metric is present and no positive threshold is met.
- `KE3_call` is missing when both KE3 metrics are missing.

### LLNA

- Input: `LLNA_EC3`.
- `LLNA_call = 1` when `LLNA_EC3 < 100`.
- `LLNA_call = 0` when `LLNA_EC3 >= 100`.
- `LLNA_call` is missing when `LLNA_EC3` is missing or cannot be parsed.
- Censored values use the mapping and fallback rules described above.

### Complete Case

- `complete_case = 1` when `KE1_metric`, `KE2_metric`, `KE3_metric`, and `LLNA_EC3` are all present.
- `complete_case = 0` otherwise.

## ICE Rules

### KE1

- Input: in vitro rows where `Assay = DPRA` and `Endpoint = Call`.
- `KE1_call = 1` if any available DPRA Call is Active.
- `KE1_call = 0` if DPRA Call exists and all available calls are Inactive.
- `KE1_call` is missing when no DPRA Call is available.
- `KE1_metric` is the median numeric response from rows where `Assay = DPRA` and `Endpoint = Depletion Lys + Cys`.

### KE2 Components

- Inputs: KeratinoSens and LuSens rows where `Endpoint = Call`.
- `KS_call` is the aggregated KeratinoSens call.
- `LuSens_call` is the aggregated LuSens call.
- Within the same component assay, Active wins over Inactive when replicate rows disagree.

### KE2 Composite

- `KE2_call = 1` if `KS_call` or `LuSens_call` is Active.
- `KE2_call = 0` only when at least one KE2 component is present and all available KE2 components are Inactive.
- `KE2_call` is missing when both `KS_call` and `LuSens_call` are missing.
- `KE2_conflict = 1` when both `KS_call` and `LuSens_call` are present and they disagree.

### KE3 Components

- Inputs: h-CLAT and U-SENS rows where `Endpoint = Call`.
- `hCLAT_call` is the aggregated h-CLAT call.
- `USENS_call` is the aggregated U-SENS call.
- Within the same component assay, Active wins over Inactive when replicate rows disagree.

### KE3 Composite

- `KE3_call = 1` if `hCLAT_call` or `USENS_call` is Active.
- `KE3_call = 0` only when at least one KE3 component is present and all available KE3 components are Inactive.
- `KE3_call` is missing when both `hCLAT_call` and `USENS_call` are missing.
- `KE3_conflict = 1` when both `hCLAT_call` and `USENS_call` are present and they disagree.

### LLNA Priority Rule

The final `LLNA_call` is assigned by priority. Lower-priority sources are used only when all higher-priority sources are missing.

1. Endpoint `Call`:
   - Active -> `LLNA_call = 1`
   - Inactive -> `LLNA_call = 0`
2. Endpoint `EPA Classification`:
   - Sensitizer -> `LLNA_call = 1`
   - Non-sensitizer -> `LLNA_call = 0`
3. Endpoint `Max stimulation index`:
   - value >= 3 -> `LLNA_call = 1`
   - value < 3 -> `LLNA_call = 0`
4. Endpoint `EC3`:
   - exact EC3 value < 100 -> `LLNA_call = 1`
   - exact EC3 value >= 100 -> `LLNA_call = 0`
   - censored values are assigned only when their bound proves the result; for example, `>100` is negative, while `>20` remains missing.
5. If all four LLNA sources are missing or indeterminate, `LLNA_call` remains missing.

The output also keeps `LLNA_call_endpoint`, `LLNA_EPA_call`, `LLNA_max_stimulation_index`, `LLNA_EC3`, their derived calls, and `LLNA_call_source` so the final call can be audited.

### Misclassified

- `Misclassified = 1` if any of `KE1_call`, `KE2_call`, or `KE3_call` differs from final `LLNA_call`.
- `Misclassified = 0` if all three KE calls match final `LLNA_call`.
- `Misclassified` is missing when any required KE call or final `LLNA_call` is missing.

### ICE Complete-Case Options

Set `ICE_COMPLETE_CASE_OPTION` in `ice_process.py` to choose one of these outputs:

- Option 1: original strict call rule. Complete when `KE1_call`, `KE2_call`, `KE3_call`, and endpoint `LLNA_call_endpoint` are all present.
- Option 2: metric/source rule. Complete when `KE1_metric`, at least one KE2 component call, at least one KE3 component call, and `LLNA_EC3` are all present.
- Option 3: broad final-LLNA rule. Complete when `KE1_call`, `KE2_call`, `KE3_call`, and final prioritized `LLNA_call` are all present.
- Option 4: conservative final rule. Complete when option 3 is true and both `KE2_conflict = 0` and `KE3_conflict = 0`. This excludes chemicals where KeratinoSens/LuSens disagree or h-CLAT/U-SENS disagree.

The script writes `complete_case_option_1`, `complete_case_option_2`, `complete_case_option_3`, and `complete_case_option_4` columns, plus a `complete_case` column for the selected option.

## Run Order

```powershell
python ice_process.py
python skinsens.py
python synthetic.py
python compare_colleague_complete_cases.py
python brute_force_ice_rules.py
```

## Notes

The scripts use consistent output column names: `Dataset`, `Chemical`, `CAS`, KE calls, and LLNA calls. Comments in the scripts are intentionally placed above each rule block so future rule changes can be made in the relevant block without rewriting the whole script.
