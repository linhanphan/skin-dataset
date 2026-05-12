import pandas as pd
import numpy as np

SKIN_FILE = "RAW_SKINSENS_DB_complete.xls"
OUTPUT_CSV = "Skin_209_endpoint_presence_from_raw.csv"


def clean_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df.loc[:, ~df.columns.duplicated()].copy()


def first_nonnull(row, cols):
    vals = [row[c] for c in cols if c in row.index and pd.notna(row[c])]
    return vals[0] if vals else np.nan


# -----------------------------
# Load SkinSensDB
# -----------------------------
# xlrd is needed for .xls files
df = clean_cols(pd.read_excel(SKIN_FILE))

# Some SkinSensDB exports repeat the header in the first data row
if len(df) > 0 and str(df.iloc[0, 0]).strip().lower() == str(df.columns[0]).strip().lower():
    df = df.iloc[1:].reset_index(drop=True)

# Standardize likely identifiers
if "CAS" in df.columns:
    df["CAS"] = df["CAS"].astype(str).str.strip()
elif "CASRN" in df.columns:
    df["CAS"] = df["CASRN"].astype(str).str.strip()
else:
    raise ValueError("No CAS/CASRN column found.")

if "Preferred_Name" in df.columns:
    df["Chemical"] = df["Preferred_Name"]
elif "Chemical_Name" in df.columns:
    df["Chemical"] = df["Chemical_Name"]
else:
    df["Chemical"] = df["CAS"]

df["Dataset"] = "SkinSensDB"

# -----------------------------
# KE1
# -----------------------------
# Typical columns: DPRA_Cys, DPRA_Lys
dpra_cols = [c for c in df.columns if c in ["DPRA_Cys", "DPRA_Lys"]]
if dpra_cols:
    df[dpra_cols] = df[dpra_cols].apply(pd.to_numeric, errors="coerce")
    df["KE1_metric"] = df[dpra_cols].mean(axis=1, skipna=True)
    df["KE1_call"] = np.where(df["KE1_metric"].notna(), (df["KE1_metric"] >= 6.38).astype(int), np.nan)
else:
    df["KE1_metric"] = np.nan
    df["KE1_call"] = np.nan

# -----------------------------
# KE2
# -----------------------------
# Typical column: KeratinoSens_LuSens_EC15
if "KeratinoSens_LuSens_EC15" in df.columns:
    df["KE2_metric"] = pd.to_numeric(df["KeratinoSens_LuSens_EC15"], errors="coerce")
    df["KE2_call"] = np.where(df["KE2_metric"].notna(), (df["KE2_metric"] <= 1000).astype(int), np.nan)
else:
    df["KE2_metric"] = np.nan
    df["KE2_call"] = np.nan

# -----------------------------
# KE3
# -----------------------------
# Typical columns: h-CLAT_U-SENS_EC150, h-CLAT_EC200
ec150_col = "h-CLAT_U-SENS_EC150"
ec200_col = "h-CLAT_EC200"

if ec150_col in df.columns:
    df[ec150_col] = pd.to_numeric(df[ec150_col], errors="coerce")
if ec200_col in df.columns:
    df[ec200_col] = pd.to_numeric(df[ec200_col], errors="coerce")

def ke3_metric(row):
    vals = []
    for c in [ec150_col, ec200_col]:
        if c in row.index and pd.notna(row[c]):
            vals.append(row[c])
    return min(vals) if vals else np.nan

df["KE3_metric"] = df.apply(ke3_metric, axis=1)

def ke3_call(row):
    ec150 = row[ec150_col] if ec150_col in row.index else np.nan
    ec200 = row[ec200_col] if ec200_col in row.index else np.nan
    if pd.notna(ec150) and ec150 <= 150:
        return 1
    if pd.notna(ec200) and ec200 <= 200:
        return 1
    if pd.notna(ec150) or pd.notna(ec200):
        return 0
    return np.nan

df["KE3_call"] = df.apply(ke3_call, axis=1)

# -----------------------------
# LLNA
# -----------------------------
if "LLNA_EC3" in df.columns:
    df["LLNA_EC3"] = pd.to_numeric(df["LLNA_EC3"], errors="coerce")
    df["LLNA_call"] = np.where(df["LLNA_EC3"].notna(), (df["LLNA_EC3"] > 0).astype(int), np.nan)
else:
    df["LLNA_EC3"] = np.nan
    df["LLNA_call"] = np.nan

# Presence flags
for col in ["KE1_metric", "KE2_metric", "KE3_metric", "LLNA_EC3"]:
    df[f"{col}__present"] = df[col].notna().astype(int)

# Optional complete-case flag
required = ["KE1_metric", "KE2_metric", "KE3_metric", "LLNA_EC3"]
df["complete_case"] = df[required].notna().all(axis=1).astype(int)

# Final output
keep = [
    "Dataset", "Chemical", "CAS",
    "KE1_call", "KE2_call", "KE3_call", "LLNA_call",
    "KE1_metric", "KE1_metric__present",
    "KE2_metric", "KE2_metric__present",
    "KE3_metric", "KE3_metric__present",
    "LLNA_EC3", "LLNA_EC3__present",
    "complete_case",
]

keep = [c for c in keep if c in df.columns]
out = df[keep].copy()
out.to_csv(OUTPUT_CSV, index=False)

print(f"Saved: {OUTPUT_CSV}")
print("Rows:", len(out))
