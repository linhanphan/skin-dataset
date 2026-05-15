import pandas as pd
import numpy as np

ICE_FILE = "RAW_ICE_skin_sensitization.xlsx"

# Change this to 1, 2, or 3 to choose the ICE complete-case rule.
# Option 1: original strict call rule: KE1_call + KE2_call + KE3_call + endpoint LLNA Call.
# Option 2: metric/source rule: KE1_metric + any KE2 component + any KE3 component + LLNA_EC3.
# Option 3: broad LLNA priority rule: KE1_call + KE2_call + KE3_call + any LLNA source
#           where LLNA source priority is Call, then EPA Classification, then EC3.
ICE_COMPLETE_CASE_OPTION = 1

OUTPUT_CSV = f"ICE_endpoint_presence_from_raw_option_{ICE_COMPLETE_CASE_OPTION}.csv"
COMPLETE_CASE_CSV = f"ICE_complete_cases_from_raw_option_{ICE_COMPLETE_CASE_OPTION}.csv"
LEGACY_OUTPUT_CSV = "ICE_endpoint_presence_from_raw.csv"
LEGACY_COMPLETE_CASE_CSV = "ICE_complete_cases_from_raw.csv"


def clean_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df.loc[:, ~df.columns.duplicated()].copy()


def clean_identifier(value):
    if pd.isna(value):
        return np.nan

    s = str(value).strip()
    if not s or s.lower() == "nan":
        return np.nan
    return s


def normalize_call(series):
    vals = []
    for v in series:
        if pd.isna(v):
            continue
        s = str(v).strip().lower()
        if s in {"active", "inactive"}:
            vals.append(s)

    if not vals:
        return np.nan
    if "active" in vals:
        return "Active"
    return "Inactive"


def binary_call(series):
    vals = []
    for v in series:
        if pd.isna(v):
            continue
        s = str(v).strip().lower()
        if s in {"active", "inactive"}:
            vals.append(s)

    if not vals:
        return np.nan
    return 1 if "active" in vals else 0


def binary_epa_classification(series):
    vals = []
    for v in series:
        if pd.isna(v):
            continue
        s = str(v).strip().lower()
        if s in {"sensitizer", "non-sensitizer", "non sensitizer", "nonsensitizer"}:
            vals.append(s)

    if not vals:
        return np.nan
    if "sensitizer" in vals:
        return 1
    return 0


# -----------------------------
# Load raw ICE sheets
# -----------------------------
df_invitro = clean_cols(pd.read_excel(ICE_FILE, sheet_name="Data_invitro"))
df_invivo = clean_cols(pd.read_excel(ICE_FILE, sheet_name="Data_invivo"))

for df in (df_invitro, df_invivo):
    df["CASRN"] = df["CASRN"].apply(clean_identifier)

# -----------------------------
# Base chemical list
# -----------------------------
chem = (
    pd.concat(
        [
            df_invitro[["CASRN", "Chemical_Name"]],
            df_invivo[["CASRN", "Chemical_Name"]],
        ],
        ignore_index=True,
    )
    .dropna(subset=["CASRN"])
    .drop_duplicates(subset=["CASRN"], keep="first")
    .rename(columns={"CASRN": "CAS", "Chemical_Name": "Chemical"})
    .reset_index(drop=True)
)

chem["Dataset"] = "ICE"

# -----------------------------
# KE1
# -----------------------------
# Rule:
# - KE1_call comes from DPRA rows where Endpoint = Call.
# - KE1_call is 1 if any available DPRA Call is Active.
# - KE1_call is 0 if DPRA Call exists and all available calls are Inactive.
# - KE1_metric is the median numeric DPRA response where Endpoint = Depletion Lys + Cys.
ke1_call = (
    df_invitro[(df_invitro["Assay"] == "DPRA") & (df_invitro["Endpoint"] == "Call")]
    .groupby("CASRN")["Reported_Response"]
    .apply(binary_call)
    .reset_index(name="KE1_call")
    .rename(columns={"CASRN": "CAS"})
)

ke1_metric = (
    df_invitro[(df_invitro["Assay"] == "DPRA") & (df_invitro["Endpoint"] == "Depletion Lys + Cys")]
    .assign(Response_num=lambda d: pd.to_numeric(d["Response"], errors="coerce"))
    .groupby("CASRN")["Response_num"]
    .median()
    .reset_index(name="KE1_metric")
    .rename(columns={"CASRN": "CAS"})
)

# -----------------------------
# KE2 components
# -----------------------------
# Rule:
# - KS_call is the aggregated KeratinoSens Call.
# - LuSens_call is the aggregated LuSens Call.
# - Within the same component assay, Active wins over Inactive when replicates disagree.
ks_call = (
    df_invitro[(df_invitro["Assay"] == "KeratinoSens") & (df_invitro["Endpoint"] == "Call")]
    .groupby("CASRN")["Reported_Response"]
    .apply(normalize_call)
    .reset_index(name="KS_call")
    .rename(columns={"CASRN": "CAS"})
)

lusens_call = (
    df_invitro[(df_invitro["Assay"] == "LuSens") & (df_invitro["Endpoint"] == "Call")]
    .groupby("CASRN")["Reported_Response"]
    .apply(normalize_call)
    .reset_index(name="LuSens_call")
    .rename(columns={"CASRN": "CAS"})
)

# -----------------------------
# KE3 components
# -----------------------------
# Rule:
# - hCLAT_call is the aggregated h-CLAT Call.
# - USENS_call is the aggregated U-SENS Call.
# - Within the same component assay, Active wins over Inactive when replicates disagree.
hclat_call = (
    df_invitro[(df_invitro["Assay"] == "h-CLAT") & (df_invitro["Endpoint"] == "Call")]
    .groupby("CASRN")["Reported_Response"]
    .apply(normalize_call)
    .reset_index(name="hCLAT_call")
    .rename(columns={"CASRN": "CAS"})
)

usens_call = (
    df_invitro[(df_invitro["Assay"] == "U-SENS") & (df_invitro["Endpoint"] == "Call")]
    .groupby("CASRN")["Reported_Response"]
    .apply(normalize_call)
    .reset_index(name="USENS_call")
    .rename(columns={"CASRN": "CAS"})
)

# -----------------------------
# LLNA
# -----------------------------
# Rule:
# - Keep the endpoint LLNA Call separately as LLNA_call_endpoint.
# - Later, final LLNA_call is assigned by priority:
#   1. Endpoint = Call, Active -> 1 and Inactive -> 0.
#   2. If Call is missing, Endpoint = EPA Classification, Sensitizer -> 1 and Non-sensitizer -> 0.
#   3. If both are missing, Endpoint = EC3, EC3 > 0 -> 1 and EC3 <= 0 -> 0.
#   4. If all LLNA sources are missing, final LLNA_call remains missing.
llna_call_endpoint = (
    df_invivo[(df_invivo["Assay"] == "LLNA") & (df_invivo["Endpoint"] == "Call")]
    .groupby("CASRN")["Response"]
    .apply(binary_call)
    .reset_index(name="LLNA_call_endpoint")
    .rename(columns={"CASRN": "CAS"})
)

llna_epa = (
    df_invivo[(df_invivo["Assay"] == "LLNA") & (df_invivo["Endpoint"] == "EPA Classification")]
    .groupby("CASRN")["Response"]
    .apply(binary_epa_classification)
    .reset_index(name="LLNA_EPA_call")
    .rename(columns={"CASRN": "CAS"})
)

llna_ec3 = (
    df_invivo[(df_invivo["Assay"] == "LLNA") & (df_invivo["Endpoint"] == "EC3")]
    .assign(Response_num=lambda d: pd.to_numeric(d["Response"], errors="coerce"))
    .groupby("CASRN")["Response_num"]
    .median()
    .reset_index(name="LLNA_EC3")
    .rename(columns={"CASRN": "CAS"})
)

# -----------------------------
# Merge everything
# -----------------------------
out = chem.copy()

for tbl in [ke1_call, ke1_metric, ks_call, lusens_call, hclat_call, usens_call, llna_call_endpoint, llna_epa, llna_ec3]:
    out = out.merge(tbl, on="CAS", how="left")

# -----------------------------
# Composite KE2 / KE3 rules
# -----------------------------
# Rule:
# - KE2_call is 1 if KeratinoSens OR LuSens is Active.
# - KE2_call is 0 only when at least one KE2 component exists and all available
#   KE2 components are Inactive.
# - KE2_conflict is 1 when both KE2 components exist and disagree.
# - KE3_call follows the same OR-positive rule for h-CLAT and U-SENS.
# - KE3_conflict is 1 when both KE3 components exist and disagree.
def make_ke2(row):
    vals = [row["KS_call"], row["LuSens_call"]]
    vals = [v for v in vals if pd.notna(v)]
    if not vals:
        return np.nan
    return 1 if "Active" in vals else 0

def make_ke3(row):
    vals = [row["hCLAT_call"], row["USENS_call"]]
    vals = [v for v in vals if pd.notna(v)]
    if not vals:
        return np.nan
    return 1 if "Active" in vals else 0

def component_conflict(row, cols):
    vals = [row[c] for c in cols if pd.notna(row[c])]
    if len(vals) < 2:
        return 0
    return int(len(set(vals)) > 1)

out["KE2_call"] = out.apply(make_ke2, axis=1)
out["KE3_call"] = out.apply(make_ke3, axis=1)
out["KE2_conflict"] = out.apply(lambda row: component_conflict(row, ["KS_call", "LuSens_call"]), axis=1)
out["KE3_conflict"] = out.apply(lambda row: component_conflict(row, ["hCLAT_call", "USENS_call"]), axis=1)

# -----------------------------
# Final LLNA priority rule
# -----------------------------
# Rule:
# - LLNA_call is the final prioritized LLNA call used by Misclassified.
# - LLNA_call_source records which source was used.
out["LLNA_EC3_call"] = np.where(out["LLNA_EC3"].notna(), (out["LLNA_EC3"] > 0).astype(int), np.nan)

out["LLNA_call"] = out["LLNA_call_endpoint"]
out["LLNA_call_source"] = pd.Series(pd.NA, index=out.index, dtype="object")
out.loc[out["LLNA_call_endpoint"].notna(), "LLNA_call_source"] = "Call"

missing_llna = out["LLNA_call"].isna() & out["LLNA_EPA_call"].notna()
out.loc[missing_llna, "LLNA_call"] = out.loc[missing_llna, "LLNA_EPA_call"]
out.loc[missing_llna, "LLNA_call_source"] = "EPA Classification"

missing_llna = out["LLNA_call"].isna() & out["LLNA_EC3_call"].notna()
out.loc[missing_llna, "LLNA_call"] = out.loc[missing_llna, "LLNA_EC3_call"]
out.loc[missing_llna, "LLNA_call_source"] = "EC3"

# -----------------------------
# Presence flags
# -----------------------------
for col in ["KE1_metric", "KS_call", "LuSens_call", "hCLAT_call", "USENS_call", "LLNA_call_endpoint", "LLNA_EPA_call", "LLNA_EC3", "LLNA_call"]:
    out[f"{col}__present"] = out[col].notna().astype(int)

# Optional discordance flag
def misclassified(row):
    llna = row["LLNA_call"]
    kes = [row["KE1_call"], row["KE2_call"], row["KE3_call"]]
    if pd.isna(llna) or any(pd.isna(v) for v in kes):
        return np.nan
    return int(any(v != llna for v in kes))

out["Misclassified"] = out.apply(misclassified, axis=1)

# -----------------------------
# Complete case options
# -----------------------------
# Option 1: original strict call rule.
out["complete_case_option_1"] = out[["KE1_call", "KE2_call", "KE3_call", "LLNA_call_endpoint"]].notna().all(axis=1).astype(int)

# Option 2: metric/source rule for comparing with metric-focused definitions.
out["complete_case_option_2"] = (
    out["KE1_metric"].notna()
    & (out["KS_call"].notna() | out["LuSens_call"].notna())
    & (out["hCLAT_call"].notna() | out["USENS_call"].notna())
    & out["LLNA_EC3"].notna()
).astype(int)

# Option 3: broad final-LLNA rule with priority Call > EPA Classification > EC3.
out["complete_case_option_3"] = out[["KE1_call", "KE2_call", "KE3_call", "LLNA_call"]].notna().all(axis=1).astype(int)

if ICE_COMPLETE_CASE_OPTION not in {1, 2, 3}:
    raise ValueError("ICE_COMPLETE_CASE_OPTION must be 1, 2, or 3.")

out["complete_case"] = out[f"complete_case_option_{ICE_COMPLETE_CASE_OPTION}"]

# Final column order
final_cols = [
    "Dataset", "Chemical", "CAS",
    "KE1_call", "KE2_call", "KE3_call", "LLNA_call", "Misclassified",
    "KE2_conflict", "KE3_conflict",
    "KE1_metric", "KE1_metric__present",
    "KS_call", "KS_call__present",
    "LuSens_call", "LuSens_call__present",
    "hCLAT_call", "hCLAT_call__present",
    "USENS_call", "USENS_call__present",
    "LLNA_call_endpoint", "LLNA_call_endpoint__present",
    "LLNA_EPA_call", "LLNA_EPA_call__present",
    "LLNA_EC3", "LLNA_EC3__present",
    "LLNA_EC3_call",
    "LLNA_call_source", "LLNA_call__present",
    "complete_case_option_1", "complete_case_option_2", "complete_case_option_3",
    "complete_case",
]

out = out[final_cols]
complete_cases = out[out["complete_case"].eq(1)].copy()

out.to_csv(OUTPUT_CSV, index=False)
complete_cases.to_csv(COMPLETE_CASE_CSV, index=False)
out.to_csv(LEGACY_OUTPUT_CSV, index=False)
complete_cases.to_csv(LEGACY_COMPLETE_CASE_CSV, index=False)

print(f"Saved: {OUTPUT_CSV}")
print(f"Saved complete cases: {COMPLETE_CASE_CSV}")
print(f"Saved legacy alias: {LEGACY_OUTPUT_CSV}")
print(f"Saved legacy complete-case alias: {LEGACY_COMPLETE_CASE_CSV}")
print("Complete case option:", ICE_COMPLETE_CASE_OPTION)
print("Rows:", len(out))
print("Complete cases:", len(complete_cases))
