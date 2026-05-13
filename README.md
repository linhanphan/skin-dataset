# Skin Sensitization Dataset Processing

This repository processes two skin sensitization sources, ICE and SkinSensDB, into assay-level chemical tables. The goal is to identify which chemicals have usable results for key assays, whether each result is positive or negative, and whether the in vitro key-event calls disagree with LLNA.

## Files

- `ice_process.py`: reads `RAW_ICE_skin_sensitization.xlsx` and writes `ICE_endpoint_presence_from_raw.csv` plus `ICE_complete_cases_from_raw.csv`.
- `skinsens.py`: reads `RAW_SKINSENS_DB_complete.xls` and writes `Skin_endpoint_presence_from_raw.csv` plus `Skin_complete_cases_from_raw.csv`.
- `synthetic.py`: reads the two processed CSV files and writes:
  - `analysis_outputs.xlsx` for full Excel analysis sheets.
  - `analysis_quick_view.csv` for quick GitHub review of complete cases.
- `compare_colleague_complete_cases.py`: reads `complete_case_chemical_lists_ICE105_Skin209.xlsx`, exports the colleague sheets to CSV, compares them with the current complete-case outputs, and writes reverse-rule diagnostics under `comparison_outputs/`.

## ICE Rules

- `KE1_call`: DPRA rows where `Endpoint = Call`.
- `KE1_metric`: median numeric response from DPRA rows where `Endpoint = Depletion Lys + Cys`.
- `KS_call`: aggregated KeratinoSens call.
- `LuSens_call`: aggregated LuSens call.
- `hCLAT_call`: aggregated h-CLAT call.
- `USENS_call`: aggregated U-SENS call.
- `KE2_call`: positive if either `KS_call` or `LuSens_call` is Active.
- `KE3_call`: positive if either `hCLAT_call` or `USENS_call` is Active.
- `LLNA_call`: LLNA rows where `Endpoint = Call`.
- `LLNA_EC3`: median numeric LLNA response where `Endpoint = EC3`.
- `Misclassified`: `1` if any KE call differs from `LLNA_call`; otherwise `0`.
- `complete_case`: `1` when `KE1_call`, `KE2_call`, `KE3_call`, and `LLNA_call` are all present.

Presence flags are created for `KE1_metric`, `KS_call`, `LuSens_call`, `hCLAT_call`, `USENS_call`, and `LLNA_EC3`.

## SkinSensDB Rules

- `KE1_metric`: mean of `DPRA_Cys` and `DPRA_Lys`.
- `KE1_call`: `1` if `KE1_metric >= 6.38`, otherwise `0`.
- `KE2_metric`: `KeratinoSens_LuSens_EC15`.
- `KE2_call`: `1` if `KE2_metric <= 1000`, otherwise `0`.
- `KE3_metric`: minimum of `h-CLAT_U-SENS_EC150` and `h-CLAT_EC200`, using whichever values are available.
- `KE3_call`: `1` if `EC150 <= 150` or `EC200 <= 200`, otherwise `0`.
- `LLNA_call`: `1` if `LLNA_EC3` is present and positive.
- `complete_case`: `1` when `KE1_call`, `KE2_call`, `KE3_call`, and `LLNA_call` are all present.

## Run Order

```powershell
python ice_process.py
python skinsens.py
python synthetic.py
python compare_colleague_complete_cases.py
```

## Notes

The scripts now use consistent output column names (`CAS`, `Chemical`, and KE/LLNA call columns). `synthetic.py` computes `misclassified` directly from the KE and LLNA calls, so it works for both ICE and SkinSensDB processed outputs.
