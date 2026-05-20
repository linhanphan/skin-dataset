import itertools
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_CSV = "ICE_endpoint_presence_from_raw.csv"
OUTPUT_DIR = Path("ice_rule_bruteforce_outputs")


def has_value(value):
    if pd.isna(value):
        return False
    return str(value).strip() != ""


def clean_binary_call(value):
    if not has_value(value):
        return np.nan

    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text in {"0", "1"}:
        return int(text)
    return value


def any_present(row, cols):
    return any(has_value(row.get(col, np.nan)) for col in cols)


def all_present(row, cols):
    return all(has_value(row.get(col, np.nan)) for col in cols)


def call_from_components(row, cols, mode):
    vals = [row[col] for col in cols if has_value(row.get(col, np.nan))]
    if not vals:
        return np.nan

    if mode == "or_positive":
        return 1 if "Active" in vals else 0

    if mode == "consensus_negative":
        return 0 if "Inactive" in vals else 1

    raise ValueError(f"Unknown component mode: {mode}")


def component_conflict(row, cols):
    vals = [row[col] for col in cols if has_value(row.get(col, np.nan))]
    if len(vals) < 2:
        return 0
    return int(len(set(vals)) > 1)


def llna_by_priority(row, priority):
    for source in priority:
        if source == "call" and has_value(row.get("LLNA_call_endpoint", np.nan)):
            return clean_binary_call(row["LLNA_call_endpoint"]), "Call"
        if source == "epa" and has_value(row.get("LLNA_EPA_call", np.nan)):
            return clean_binary_call(row["LLNA_EPA_call"]), "EPA Classification"
        if source == "ec3" and has_value(row.get("LLNA_EC3_call", np.nan)):
            return clean_binary_call(row["LLNA_EC3_call"]), "EC3"
    return np.nan, ""


def apply_rule(df, rule):
    d = df.copy()

    d["bf_KE2_call"] = d.apply(
        lambda row: call_from_components(row, ["KS_call", "LuSens_call"], rule["ke2_mode"]),
        axis=1,
    )
    d["bf_KE3_call"] = d.apply(
        lambda row: call_from_components(row, ["hCLAT_call", "USENS_call"], rule["ke3_mode"]),
        axis=1,
    )
    d["bf_KE2_conflict"] = d.apply(
        lambda row: component_conflict(row, ["KS_call", "LuSens_call"]),
        axis=1,
    )
    d["bf_KE3_conflict"] = d.apply(
        lambda row: component_conflict(row, ["hCLAT_call", "USENS_call"]),
        axis=1,
    )

    llna = d.apply(lambda row: llna_by_priority(row, rule["llna_priority"]), axis=1)
    d["bf_LLNA_call"] = [item[0] for item in llna]
    d["bf_LLNA_source"] = [item[1] for item in llna]

    if rule["complete_mode"] == "call_based":
        complete = d.apply(
            lambda row: all_present(row, ["KE1_call", "bf_KE2_call", "bf_KE3_call", "bf_LLNA_call"]),
            axis=1,
        )
    elif rule["complete_mode"] == "metric_source_based":
        complete = d.apply(
            lambda row: has_value(row.get("KE1_metric", np.nan))
            and any_present(row, ["KS_call", "LuSens_call"])
            and any_present(row, ["hCLAT_call", "USENS_call"])
            and has_value(row.get("LLNA_EC3", np.nan)),
            axis=1,
        )
    else:
        raise ValueError(f"Unknown complete mode: {rule['complete_mode']}")

    if rule["exclude_conflicts"]:
        complete = complete & d["bf_KE2_conflict"].eq(0) & d["bf_KE3_conflict"].eq(0)

    d["bf_complete_case"] = complete.astype(int)
    d["bf_misclassified"] = d.apply(
        lambda row: np.nan
        if not all_present(row, ["KE1_call", "bf_KE2_call", "bf_KE3_call", "bf_LLNA_call"])
        else int(
            clean_binary_call(row["KE1_call"]) != clean_binary_call(row["bf_LLNA_call"])
            or clean_binary_call(row["bf_KE2_call"]) != clean_binary_call(row["bf_LLNA_call"])
            or clean_binary_call(row["bf_KE3_call"]) != clean_binary_call(row["bf_LLNA_call"])
        ),
        axis=1,
    )

    return d


df = pd.read_csv(INPUT_CSV, dtype=object)

# Recompute EC3-derived call here so this script can run even if the input was
# produced by an older ice_process.py.
df["LLNA_EC3_num"] = pd.to_numeric(df.get("LLNA_EC3", np.nan), errors="coerce")
df["LLNA_EC3_call"] = np.where(df["LLNA_EC3_num"].notna(), (df["LLNA_EC3_num"] > 0).astype(int), np.nan)

if "LLNA_call_endpoint" not in df.columns:
    df["LLNA_call_endpoint"] = df.get("LLNA_call", np.nan)
if "LLNA_EPA_call" not in df.columns:
    df["LLNA_EPA_call"] = np.nan

OUTPUT_DIR.mkdir(exist_ok=True)

component_modes = ["or_positive", "consensus_negative"]
conflict_options = [False, True]
complete_modes = ["call_based", "metric_source_based"]
llna_priorities = [
    ("call",),
    ("ec3",),
    ("epa",),
    ("call", "epa", "ec3"),
    ("call", "ec3"),
    ("ec3", "call"),
    ("call", "epa"),
    ("epa", "ec3"),
]

summary_rows = []

for idx, (ke2_mode, ke3_mode, exclude_conflicts, complete_mode, llna_priority) in enumerate(
    itertools.product(component_modes, component_modes, conflict_options, complete_modes, llna_priorities),
    start=1,
):
    rule = {
        "rule_id": f"rule_{idx:03d}",
        "ke2_mode": ke2_mode,
        "ke3_mode": ke3_mode,
        "exclude_conflicts": exclude_conflicts,
        "complete_mode": complete_mode,
        "llna_priority": llna_priority,
    }
    result = apply_rule(df, rule)
    complete_cases = result[result["bf_complete_case"].eq(1)].copy()

    summary_rows.append(
        {
            "rule_id": rule["rule_id"],
            "complete_count": len(complete_cases),
            "misclassified_count": int(complete_cases["bf_misclassified"].fillna(0).sum()),
            "ke2_mode": ke2_mode,
            "ke3_mode": ke3_mode,
            "exclude_conflicts": exclude_conflicts,
            "complete_mode": complete_mode,
            "llna_priority": " > ".join(llna_priority),
        }
    )

    complete_cases.to_csv(OUTPUT_DIR / f"{rule['rule_id']}_complete_cases.csv", index=False)

summary = pd.DataFrame(summary_rows).sort_values(
    ["complete_count", "rule_id"], ascending=[False, True]
)
summary.to_csv(OUTPUT_DIR / "ice_rule_bruteforce_summary.csv", index=False)

grouped = (
    summary.groupby(
        [
            "complete_count",
            "misclassified_count",
            "exclude_conflicts",
            "complete_mode",
            "llna_priority",
        ],
        dropna=False,
    )
    .agg(
        n_rules=("rule_id", "count"),
        example_rule_id=("rule_id", "first"),
        ke2_modes=("ke2_mode", lambda s: ", ".join(sorted(set(s)))),
        ke3_modes=("ke3_mode", lambda s: ", ".join(sorted(set(s)))),
    )
    .reset_index()
    .sort_values(["complete_count", "misclassified_count"], ascending=[False, True])
)
grouped.to_csv(OUTPUT_DIR / "ice_rule_bruteforce_grouped_summary.csv", index=False)

notes = """# ICE Rule Brute-Force Notes

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
"""
(OUTPUT_DIR / "README.md").write_text(notes, encoding="utf-8")

print(f"Saved summary: {OUTPUT_DIR / 'ice_rule_bruteforce_summary.csv'}")
print(f"Saved grouped summary: {OUTPUT_DIR / 'ice_rule_bruteforce_grouped_summary.csv'}")
print(f"Saved per-rule complete-case CSV files under: {OUTPUT_DIR}")
print()
print(summary.to_string(index=False))
