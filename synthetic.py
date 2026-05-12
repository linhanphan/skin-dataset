import pandas as pd, numpy as np, math
from scipy.stats import fisher_exact

ice = pd.read_csv("ICE_105_endpoint_presence_from_raw.csv")
skin = pd.read_csv("Skin_209_endpoint_presence_from_raw.csv")

required = ["KE1_call","KE2_call","KE3_call","LLNA_call","misclassified"]

def make_pattern_df(df, cas_col, chem_col):
    d = df[df[required].notna().all(axis=1)].copy()
    d["pattern"] = d[["KE1_call","KE2_call","KE3_call"]].astype(int).astype(str).agg("".join, axis=1)
    d["concordant"] = d["pattern"].isin(["000","111"])
    d["n_pos"] = d[["KE1_call","KE2_call","KE3_call"]].sum(axis=1).astype(int)
    d["CAS"] = d[cas_col]
    d["Chemical"] = d[chem_col]
    return d

icep = make_pattern_df(ice, "CASRN", "Chemical_Name")
skinp = make_pattern_df(skin, "CAS No", "Chemical_Name")

def or_ci(a,b,c,d):
    OR = (a*d)/(b*c)
    se = math.sqrt(1/a + 1/b + 1/c + 1/d)
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

with pd.ExcelWriter("analysis_outputs.xlsx") as writer:
    icep.to_excel(writer, "ICE_complete_case", index=False)
    skinp.to_excel(writer, "Skin_complete_case", index=False)
    pd.DataFrame([ice_stats]).to_excel(writer, "ICE_concordance", index=False)
    pd.DataFrame([skin_stats]).to_excel(writer, "Skin_concordance", index=False)
    ice_pattern_errors.to_excel(writer, "ICE_pattern_errors")
    skin_pattern_errors.to_excel(writer, "Skin_pattern_errors")
    ice_pos_errors.to_excel(writer, "ICE_pos_errors")
    skin_pos_errors.to_excel(writer, "Skin_pos_errors")
    ice_single.to_excel(writer, "ICE_single_positive")
    skin_single.to_excel(writer, "Skin_single_positive")
    ice_ke3_fail.to_excel(writer, "ICE_KE3_only_fail", index=False)
    skin_ke3_fail.to_excel(writer, "Skin_KE3_only_fail", index=False)
