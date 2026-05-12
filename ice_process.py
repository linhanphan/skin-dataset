import pandas as pd
import numpy as np

ICE_FILE = "RAW_ICE_skin_sensitization.xlsx"
OUTPUT_CSV = "ICE_105_endpoint_presence_from_raw.csv"


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
llna_call = (
    df_invivo[(df_invivo["Assay"] == "LLNA") & (df_invivo["Endpoint"] == "Call")]
    .groupby("CASRN")["Response"]
    .apply(binary_call)
    .reset_index(name="LLNA_call")
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

for tbl in [ke1_call, ke1_metric, ks_call, lusens_call, hclat_call, usens_call, llna_call, llna_ec3]:
    out = out.merge(tbl, on="CAS", how="left")

# -----------------------------
# Composite KE2 / KE3 rules
# -----------------------------
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

out["KE2_call"] = out.apply(make_ke2, axis=1)
out["KE3_call"] = out.apply(make_ke3, axis=1)

# -----------------------------
# Presence flags
# -----------------------------
for col in ["KE1_metric", "KS_call", "LuSens_call", "hCLAT_call", "USENS_call", "LLNA_EC3"]:
    out[f"{col}__present"] = out[col].notna().astype(int)

# Optional discordance flag
def misclassified(row):
    llna = row["LLNA_call"]
    kes = [row["KE1_call"], row["KE2_call"], row["KE3_call"]]
    if pd.isna(llna) or any(pd.isna(v) for v in kes):
        return np.nan
    return int(any(v != llna for v in kes))

out["Misclassified"] = out.apply(misclassified, axis=1)

# Final column order
final_cols = [
    "Dataset", "Chemical", "CAS",
    "KE1_call", "KE2_call", "KE3_call", "LLNA_call", "Misclassified",
    "KE1_metric", "KE1_metric__present",
    "KS_call", "KS_call__present",
    "LuSens_call", "LuSens_call__present",
    "hCLAT_call", "hCLAT_call__present",
    "USENS_call", "USENS_call__present",
    "LLNA_EC3", "LLNA_EC3__present",
]

out = out[final_cols]
out.to_csv(OUTPUT_CSV, index=False)

print(f"Saved: {OUTPUT_CSV}")
print("Rows:", len(out))
