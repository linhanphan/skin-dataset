import pandas as pd, numpy as np, math
from scipy.stats import fisher_exact

ice = pd.read_csv("ICE_endpoint_presence_from_raw.csv")
skin = pd.read_csv("Skin_endpoint_presence_from_raw.csv")

call_cols = ["KE1_call", "KE2_call", "KE3_call", "LLNA_call"]

def make_pattern_df(df, cas_col, chem_col):
    missing = [c for c in call_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required call columns: {missing}")

    d = df[df[call_cols].notna().all(axis=1)].copy()
    d[call_cols] = d[call_cols].astype(int)
    d["misclassified"] = (
        d[["KE1_call", "KE2_call", "KE3_call"]]
        .ne(d["LLNA_call"], axis=0)
        .any(axis=1)
        .astype(int)
    )
    d["pattern"] = d[["KE1_call","KE2_call","KE3_call"]].astype(str).agg("".join, axis=1)
    d["concordant"] = d["pattern"].isin(["000","111"])
    d["n_pos"] = d[["KE1_call","KE2_call","KE3_call"]].sum(axis=1).astype(int)
    d["CAS"] = d[cas_col]
    d["Chemical"] = d[chem_col]
    return d

icep = make_pattern_df(ice, "CAS", "Chemical")
skinp = make_pattern_df(skin, "CAS", "Chemical")

def or_ci(a,b,c,d):
    # Use a small continuity correction for the Wald CI when any cell is zero.
    aa, bb, cc, dd = (a, b, c, d) if min(a, b, c, d) > 0 else (a + 0.5, b + 0.5, c + 0.5, d + 0.5)
    OR = (aa * dd) / (bb * cc)
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    return OR, math.exp(math.log(OR)-1.96*se), math.exp(math.log(OR)+1.96*se)

def concordance_stats(d):
    a = int(d.loc[~d["concordant"],"misclassified"].sum())
    b = int((~d["concordant"]).sum() - a)
    c = int(d.loc[d["concordant"],"misclassified"].sum())
    dd = int(d["concordant"].sum() - c)
    OR, p = fisher_exact([[a,b],[c,dd]])
    OR2, l, u = or_ci(a,b,c,dd)
    return {
        "con_n": int(d["concordant"].sum()),
        "con_err": c,
        "con_rate": c/d["concordant"].sum(),
        "disc_n": int((~d["concordant"]).sum()),
        "disc_err": a,
        "disc_rate": a/(~d["concordant"]).sum(),
        "OR": OR,
        "CI_low": l,
        "CI_high": u,
        "p": p
    }

def pattern_error_table(d):
    g = d.groupby("pattern")["misclassified"].agg(["size","sum","mean"])
    g = g.reindex(["000","001","010","011","100","101","110","111"])
    g["error_pct"] = (g["mean"]*100).round(1)
    return g

def positivity_stats(d):
    g = d.groupby("n_pos")["misclassified"].agg(["size","sum","mean"])
    g = g.reindex([1,2,3])
    g["error_pct"] = (g["mean"]*100).round(1)
    return g

ice_stats = concordance_stats(icep)
skin_stats = concordance_stats(skinp)

ice_pattern_errors = pattern_error_table(icep)
skin_pattern_errors = pattern_error_table(skinp)

ice_pos_errors = positivity_stats(icep)
skin_pos_errors = positivity_stats(skinp)

ice_single = ice_pattern_errors.loc[["100","010","001"]]
skin_single = skin_pattern_errors.loc[["100","010","001"]]

ice_ke3_fail = icep[(icep["pattern"]=="001") & (icep["misclassified"]==1)]
skin_ke3_fail = skinp[(skinp["pattern"]=="001") & (skinp["misclassified"]==1)]

quick_cols = [
    "Dataset", "Chemical", "CAS",
    "KE1_call", "KE2_call", "KE3_call", "LLNA_call",
    "pattern", "n_pos", "concordant", "misclassified",
]
quick_view = pd.concat([icep[quick_cols], skinp[quick_cols]], ignore_index=True)
quick_view.to_csv("analysis_quick_view.csv", index=False)

with pd.ExcelWriter("analysis_outputs.xlsx") as writer:
    icep.to_excel(writer, sheet_name="ICE_complete_case", index=False)
    skinp.to_excel(writer, sheet_name="Skin_complete_case", index=False)
    pd.DataFrame([ice_stats]).to_excel(writer, sheet_name="ICE_concordance", index=False)
    pd.DataFrame([skin_stats]).to_excel(writer, sheet_name="Skin_concordance", index=False)
    ice_pattern_errors.to_excel(writer, sheet_name="ICE_pattern_errors")
    skin_pattern_errors.to_excel(writer, sheet_name="Skin_pattern_errors")
    ice_pos_errors.to_excel(writer, sheet_name="ICE_pos_errors")
    skin_pos_errors.to_excel(writer, sheet_name="Skin_pos_errors")
    ice_single.to_excel(writer, sheet_name="ICE_single_positive")
    skin_single.to_excel(writer, sheet_name="Skin_single_positive")
    ice_ke3_fail.to_excel(writer, sheet_name="ICE_KE3_only_fail", index=False)
    skin_ke3_fail.to_excel(writer, sheet_name="Skin_KE3_only_fail", index=False)
