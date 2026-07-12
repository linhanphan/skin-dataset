import pandas as pd
import numpy as np
import re

SKIN_FILE = "RAW_SKINSENS_DB_complete.xls"
OUTPUT_CSV = "Skin_endpoint_presence_from_raw.csv"
COMPLETE_CASE_CSV = "Skin_complete_cases_from_raw.csv"

# Censored numeric values in the raw file are values such as ">2000" or "<179".
# Do not edit the raw file by hand. Add exact text mappings here when the team
# wants a specific replacement value. Values not listed here use the fallback
# offsets below: ">x" becomes x + 1, and "<x" becomes x - 1.
CENSORED_VALUE_MAP = {
    ">2000": 2001,
    # Add more exact mappings as needed, for example:
    # "<192": 191,
}

CENSORED_GREATER_THAN_OFFSET = 1
CENSORED_LESS_THAN_OFFSET = -1


def clean_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df.loc[:, ~df.columns.duplicated()].copy()


def first_nonnull(row, cols):
    vals = [row[c] for c in cols if c in row.index and pd.notna(row[c])]
    return vals[0] if vals else np.nan


def clean_cas(value):
    if pd.isna(value):
        return np.nan

    s = str(value).strip()
    if not s or s.lower() == "nan":
        return np.nan

    # Some CAS values are auto-converted by Excel into dates, e.g. 59-02-9
    # becomes 1959-02-09 00:00:00. Recover the likely CAS format.
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?: 00:00:00)?", s)
    if m:
        year, month, day = (int(part) for part in m.groups())
        prefix = year - 1900 if 1900 <= year <= 1999 else year
        return f"{prefix}-{month:02d}-{day}"

    return s


def parse_censored_number(value):
    if pd.isna(value):
        return np.nan

    s = str(value).strip()
    if not s or s.lower() in {"nan", "nd", "nc", "idr", "na", "n/a"}:
        return np.nan

    if s in CENSORED_VALUE_MAP:
        return CENSORED_VALUE_MAP[s]

    # Keep this intentionally simple and easy to change:
    # Exact mappings above win first. Otherwise ">2000" becomes 2001,
    # and "<179" becomes 178.
    # This lets threshold rules include censored values without editing raw data.
    m = re.fullmatch(r"([<>]=?)\s*([-+]?\d+(?:\.\d+)?)", s)
    if m:
        sign, number = m.groups()
        number = float(number)
        if sign.startswith(">"):
            return number + CENSORED_GREATER_THAN_OFFSET
        return number + CENSORED_LESS_THAN_OFFSET

    return pd.to_numeric(s, errors="coerce")


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
    df["CAS"] = df["CAS"].apply(clean_cas)
elif "CASRN" in df.columns:
    df["CAS"] = df["CASRN"].apply(clean_cas)
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
# Rule:
# - KE1_metric is the mean of DPRA_Cys and DPRA_Lys when at least one is present.
# - KE1_call is 1 when KE1_metric >= 6.38.
# - KE1_call is 0 when KE1_metric < 6.38.
# - KE1_call is missing when KE1_metric is missing.
dpra_cols = [c for c in df.columns if c in ["DPRA_Cys", "DPRA_Lys"]]
if dpra_cols:
    df[dpra_cols] = df[dpra_cols].apply(lambda col: col.apply(parse_censored_number))
    df["KE1_metric"] = df[dpra_cols].mean(axis=1, skipna=True)
    df["KE1_call"] = np.where(df["KE1_metric"].notna(), (df["KE1_metric"] >= 6.38).astype(int), np.nan)
else:
    df["KE1_metric"] = np.nan
    df["KE1_call"] = np.nan

# -----------------------------
# KE2
# -----------------------------
# Rule:
# - KE2_metric comes from KeratinoSens_LuSens_EC15.
# - Censored values such as ">2000" are parsed in code and count as present.
# - KE2_call is 1 when KE2_metric <= 1000.
# - KE2_call is 0 when KE2_metric > 1000.
# - KE2_call is missing when KE2_metric is missing.
if "KeratinoSens_LuSens_EC15" in df.columns:
    df["KE2_metric"] = df["KeratinoSens_LuSens_EC15"].apply(parse_censored_number)
    df["KE2_call"] = np.where(df["KE2_metric"].notna(), (df["KE2_metric"] <= 1000).astype(int), np.nan)
else:
    df["KE2_metric"] = np.nan
    df["KE2_call"] = np.nan

# -----------------------------
# KE3
# -----------------------------
# Rule:
# - KE3_metric is the minimum of h-CLAT_U-SENS_EC150 and h-CLAT_EC200,
#   using whichever values are present.
# - Censored values such as ">922.33" are parsed in code and count as present.
# - KE3_call is 1 when EC150 <= 150 or EC200 <= 200.
# - KE3_call is 0 when at least one KE3 metric is present and no positive
#   threshold is met.
# - KE3_call is missing when both KE3 metrics are missing.
ec150_col = "h-CLAT_U-SENS_EC150"
ec200_col = "h-CLAT_EC200"

if ec150_col in df.columns:
    df[ec150_col] = df[ec150_col].apply(parse_censored_number)
if ec200_col in df.columns:
    df[ec200_col] = df[ec200_col].apply(parse_censored_number)

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
# Rule:
# - LLNA_EC3 is parsed as a numeric metric.
# - LLNA_call is 1 when LLNA_EC3 < 100.
# - LLNA_call is 0 when LLNA_EC3 >= 100.
# - LLNA_call is missing when LLNA_EC3 is missing.
# - Censored values use the mapping/fallback rule near the top of this file.
if "LLNA_EC3" in df.columns:
    df["LLNA_EC3"] = df["LLNA_EC3"].apply(parse_censored_number)
    df["LLNA_call"] = np.where(df["LLNA_EC3"].notna(), (df["LLNA_EC3"] < 100).astype(int), np.nan)
else:
    df["LLNA_EC3"] = np.nan
    df["LLNA_call"] = np.nan

# Presence flags
for col in ["KE1_metric", "KE2_metric", "KE3_metric", "LLNA_EC3"]:
    df[f"{col}__present"] = df[col].notna().astype(int)

# Complete cases require all four metric/evidence columns to be present.
required_metrics = ["KE1_metric", "KE2_metric", "KE3_metric", "LLNA_EC3"]
df["complete_case"] = df[required_metrics].notna().all(axis=1).astype(int)

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
complete_cases = out[out["complete_case"].eq(1)].copy()

out.to_csv(OUTPUT_CSV, index=False)
complete_cases.to_csv(COMPLETE_CASE_CSV, index=False)

print(f"Saved: {OUTPUT_CSV}")
print(f"Saved complete cases: {COMPLETE_CASE_CSV}")
print("Rows:", len(out))
print("Complete cases:", len(complete_cases))
