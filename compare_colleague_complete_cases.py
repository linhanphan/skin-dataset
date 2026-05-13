from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import pandas as pd


DEFAULT_WORKBOOK = "complete_case_chemical_lists_ICE105_Skin209.xlsx"
DEFAULT_OUTPUT_DIR = "comparison_outputs"

COLLEAGUE_ICE_SHEET = "ICE_105"
COLLEAGUE_SKIN_SHEET = "SkinSensDB_209"

OUR_ICE_COMPLETE = "ICE_complete_cases_from_raw.csv"
OUR_SKIN_COMPLETE = "Skin_complete_cases_from_raw.csv"
OUR_ICE_FULL = "ICE_endpoint_presence_from_raw.csv"
OUR_SKIN_FULL = "Skin_endpoint_presence_from_raw.csv"


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "nat", "none"}


def clean_text(value: object) -> str:
    if is_missing(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def clean_call(value: object) -> str:
    text = clean_text(value)
    if text.endswith(".0"):
        return text[:-2]
    return text


def normalize_cas(value: object) -> str:
    if is_missing(value):
        return ""

    if isinstance(value, pd.Timestamp):
        year = int(value.year)
        prefix = year - 1900 if 1900 <= year <= 1999 else year
        return f"{prefix}-{value.month:02d}-{value.day}"

    text = clean_text(value)
    if text.lower() == "nan":
        return ""

    # Excel sometimes auto-converts CAS values like 94-09-7 to dates.
    # Pandas may render those as YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?: 00:00:00)?", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        prefix = year - 1900 if 1900 <= year <= 1999 else year
        return f"{prefix}-{month:02d}-{day}"

    return text


def comparison_key(row: pd.Series) -> str:
    cas = normalize_cas(row.get("CAS", ""))
    if cas:
        return f"CAS:{cas.upper()}"

    chemical = clean_text(row.get("Chemical", ""))
    return f"CHEM:{chemical.upper()}"


def has_value(row: pd.Series, column: str) -> bool:
    return column in row.index and not is_missing(row[column])


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=object, keep_default_na=False)


def read_colleague_sheet(workbook: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]
    return df.where(pd.notna(df), "")


def keyed_rows(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {comparison_key(row): row for _, row in df.iterrows()}


def add_our_full_fields(row: pd.Series, full_row: pd.Series | None) -> dict[str, object]:
    out = row.to_dict()
    if full_row is None:
        out["our_full_complete_case"] = "not_found_in_our_full_output"
        return out

    out["our_full_complete_case"] = clean_text(full_row.get("complete_case", ""))
    for col in [
        "KE1_call",
        "KE2_call",
        "KE3_call",
        "LLNA_call",
        "KE1_metric",
        "KE2_metric",
        "KE3_metric",
        "LLNA_EC3",
        "KS_call",
        "LuSens_call",
        "hCLAT_call",
        "USENS_call",
    ]:
        if col in full_row.index:
            out[f"our_full_{col}"] = full_row[col]
    return out


def compare_dataset(
    name: str,
    colleague: pd.DataFrame,
    ours_complete: pd.DataFrame,
    ours_full: pd.DataFrame,
    output_dir: Path,
) -> dict[str, int | str]:
    colleague_by_key = keyed_rows(colleague)
    ours_complete_by_key = keyed_rows(ours_complete)
    ours_full_by_key = keyed_rows(ours_full)

    common_keys = sorted(set(colleague_by_key) & set(ours_complete_by_key))
    colleague_only_keys = sorted(set(colleague_by_key) - set(ours_complete_by_key))
    ours_only_keys = sorted(set(ours_complete_by_key) - set(colleague_by_key))

    colleague_only = [
        add_our_full_fields(colleague_by_key[key], ours_full_by_key.get(key))
        for key in colleague_only_keys
    ]
    ours_only = [ours_complete_by_key[key].to_dict() for key in ours_only_keys]
    common = [colleague_by_key[key].to_dict() for key in common_keys]

    pd.DataFrame(colleague_only).to_csv(output_dir / f"{name}_colleague_only.csv", index=False)
    pd.DataFrame(ours_only).to_csv(output_dir / f"{name}_ours_only.csv", index=False)
    pd.DataFrame(common).to_csv(output_dir / f"{name}_common.csv", index=False)

    return {
        "dataset": name,
        "colleague_count": len(colleague),
        "ours_count": len(ours_complete),
        "common_count": len(common_keys),
        "colleague_only_count": len(colleague_only_keys),
        "ours_only_count": len(ours_only_keys),
    }


def llna_from_call_or_ec3(row: pd.Series) -> tuple[str, str]:
    if has_value(row, "LLNA_EC3"):
        try:
            return ("1" if float(row["LLNA_EC3"]) > 0 else "0", "LLNA_EC3")
        except ValueError:
            pass
    return clean_call(row.get("LLNA_call", "")), "LLNA_call"


def consensus_call_from_components(values: list[object]) -> str:
    calls = [clean_text(value).lower() for value in values if not is_missing(value)]
    if not calls:
        return ""
    if "inactive" in calls:
        return "0"
    if "active" in calls:
        return "1"
    return ""


def or_call_from_components(values: list[object]) -> str:
    calls = [clean_text(value).lower() for value in values if not is_missing(value)]
    if not calls:
        return ""
    if "active" in calls:
        return "1"
    if "inactive" in calls:
        return "0"
    return ""


def write_ice_rule_diagnostics(
    colleague_ice: pd.DataFrame,
    ice_full: pd.DataFrame,
    output_dir: Path,
) -> dict[str, int]:
    full_by_key = keyed_rows(ice_full)
    rows: list[dict[str, object]] = []
    or_mismatches: list[dict[str, object]] = []
    consensus_mismatches: list[dict[str, object]] = []

    for _, colleague_row in colleague_ice.iterrows():
        full_row = full_by_key.get(comparison_key(colleague_row))
        if full_row is None:
            continue

        colleague_ke1 = clean_call(colleague_row.get("KE1_call", ""))
        colleague_ke2 = clean_call(colleague_row.get("KE2_call", ""))
        colleague_ke3 = clean_call(colleague_row.get("KE3_call", ""))
        current_ke1 = clean_call(full_row.get("KE1_call", ""))
        current_ke2_or = or_call_from_components(
            [full_row.get("KS_call", ""), full_row.get("LuSens_call", "")]
        )
        current_ke3_or = or_call_from_components(
            [full_row.get("hCLAT_call", ""), full_row.get("USENS_call", "")]
        )
        current_ke2_consensus = consensus_call_from_components(
            [full_row.get("KS_call", ""), full_row.get("LuSens_call", "")]
        )
        current_ke3_consensus = consensus_call_from_components(
            [full_row.get("hCLAT_call", ""), full_row.get("USENS_call", "")]
        )

        out = {
            "CAS": colleague_row.get("CAS", ""),
            "Chemical": colleague_row.get("Chemical", ""),
            "colleague_KE1_call": colleague_ke1,
            "colleague_KE2_call": colleague_ke2,
            "colleague_KE3_call": colleague_ke3,
            "current_KE1_call": current_ke1,
            "current_KE2_or_call": current_ke2_or,
            "current_KE3_or_call": current_ke3_or,
            "current_KE2_consensus_call": current_ke2_consensus,
            "current_KE3_consensus_call": current_ke3_consensus,
            "KS_call": full_row.get("KS_call", ""),
            "LuSens_call": full_row.get("LuSens_call", ""),
            "hCLAT_call": full_row.get("hCLAT_call", ""),
            "USENS_call": full_row.get("USENS_call", ""),
            "LLNA_call": full_row.get("LLNA_call", ""),
            "LLNA_EC3": full_row.get("LLNA_EC3", ""),
        }
        rows.append(out)

        for col, colleague_value, current_value in [
            ("KE1_call", colleague_ke1, current_ke1),
            ("KE2_call", colleague_ke2, current_ke2_or),
            ("KE3_call", colleague_ke3, current_ke3_or),
        ]:
            if colleague_value != current_value:
                mismatch = out.copy()
                mismatch["mismatch_column"] = col
                mismatch["colleague_value"] = colleague_value
                mismatch["current_or_value"] = current_value
                or_mismatches.append(mismatch)

        for col, colleague_value, consensus_value in [
            ("KE1_call", colleague_ke1, current_ke1),
            ("KE2_call", colleague_ke2, current_ke2_consensus),
            ("KE3_call", colleague_ke3, current_ke3_consensus),
        ]:
            if colleague_value != consensus_value:
                mismatch = out.copy()
                mismatch["mismatch_column"] = col
                mismatch["colleague_value"] = colleague_value
                mismatch["current_consensus_value"] = consensus_value
                consensus_mismatches.append(mismatch)

    pd.DataFrame(rows).to_csv(output_dir / "ICE_colleague_rule_diagnostics.csv", index=False)
    pd.DataFrame(or_mismatches).to_csv(
        output_dir / "ICE_colleague_mismatches_current_or_rule.csv", index=False
    )
    pd.DataFrame(consensus_mismatches).to_csv(
        output_dir / "ICE_colleague_mismatches_consensus_rule.csv", index=False
    )
    return {
        "current_or_mismatch_count": len(or_mismatches),
        "consensus_mismatch_count": len(consensus_mismatches),
    }


def add_reverse_ice_fields(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        out = row.to_dict()
        ke1 = clean_call(row.get("KE1_call", ""))
        ke2 = clean_call(row.get("KE2_call", ""))
        ke3 = clean_call(row.get("KE3_call", ""))
        llna, source = llna_from_call_or_ec3(row)

        out["reverse_pattern"] = f"{ke1}{ke2}{ke3}"
        out["reverse_LLNA_call"] = llna
        out["reverse_LLNA_source"] = source
        out["reverse_misclassified"] = int(any(ke != llna for ke in [ke1, ke2, ke3]))
        rows.append(out)
    return pd.DataFrame(rows)


def write_reverse_rule_outputs(
    ice_full: pd.DataFrame,
    colleague_ice: pd.DataFrame,
    output_dir: Path,
) -> tuple[int, int]:
    candidate = ice_full[
        ice_full.apply(
            lambda row: has_value(row, "KE1_call")
            and has_value(row, "KE2_call")
            and has_value(row, "KE3_call")
            and (has_value(row, "LLNA_call") or has_value(row, "LLNA_EC3")),
            axis=1,
        )
    ].copy()

    candidate = add_reverse_ice_fields(candidate)
    colleague_keys = set(keyed_rows(colleague_ice))
    not_in_colleague = candidate[
        ~candidate.apply(lambda row: comparison_key(row) in colleague_keys, axis=1)
    ].copy()

    candidate.to_csv(output_dir / "ICE_reverse_candidate_llna_call_or_ec3.csv", index=False)
    not_in_colleague.to_csv(output_dir / "ICE_reverse_candidate_not_in_colleague.csv", index=False)
    return len(candidate), len(not_in_colleague)


def write_ice_colleague_with_our_fields(
    colleague_ice: pd.DataFrame,
    ice_full: pd.DataFrame,
    output_dir: Path,
) -> None:
    full_by_key = keyed_rows(ice_full)
    rows = []
    for _, row in colleague_ice.iterrows():
        full = full_by_key.get(comparison_key(row))
        out = {
            "CAS": row.get("CAS", ""),
            "Chemical": row.get("Chemical", ""),
            "colleague_pattern": row.get("Pattern", ""),
            "colleague_LLNA": row.get("LLNA_call", ""),
        }
        if full is not None:
            out["ours_pattern"] = "".join(
                clean_call(full.get(col, "")) for col in ["KE1_call", "KE2_call", "KE3_call"]
            )
            out["ours_LLNA_call"] = full.get("LLNA_call", "")
            out["ours_LLNA_EC3"] = full.get("LLNA_EC3", "")
            out["KE1_metric"] = full.get("KE1_metric", "")
        rows.append(out)

    pd.DataFrame(rows).to_csv(output_dir / "ICE_colleague_with_our_fields.csv", index=False)


def write_markdown_summary(
    output_dir: Path,
    summary: list[dict[str, int | str]],
    reverse_candidate_count: int,
    reverse_extra_count: int,
    rule_diagnostics: dict[str, int],
) -> None:
    by_dataset = {str(row["dataset"]): row for row in summary}
    ice = by_dataset["ICE"]
    skin = by_dataset["SkinSensDB"]

    text = f"""# Complete Case Comparison Summary

Source workbook: `{DEFAULT_WORKBOOK}`

## Direct Comparison

| Dataset | Colleague count | Current count | Common | Colleague only | Current only |
| --- | ---: | ---: | ---: | ---: | ---: |
| ICE | {ice["colleague_count"]} | {ice["ours_count"]} | {ice["common_count"]} | {ice["colleague_only_count"]} | {ice["ours_only_count"]} |
| SkinSensDB | {skin["colleague_count"]} | {skin["ours_count"]} | {skin["common_count"]} | {skin["colleague_only_count"]} | {skin["ours_only_count"]} |

## SkinSensDB

The current 208 SkinSensDB complete cases are all present in the colleague sheet after normalizing Excel-converted CAS dates.

The one extra colleague row is `2-(4-Amino-2nitro-phenylamino)-ethanol`. Current output has KE1, KE3, and LLNA, but missing KE2. The colleague sheet assigns `KE2_call=0`, so their rule likely treated missing KE2 as inactive/negative.

## ICE

All 63 colleague-only ICE rows are present in the current full ICE output, have `LLNA_EC3`, and are missing `LLNA_call`. This suggests the colleague derived LLNA from EC3 when LLNA call was absent.

The colleague ICE calls do not fully match the current OR rule for KE2/KE3:

- Current OR rule mismatches against the colleague sheet: {rule_diagnostics["current_or_mismatch_count"]}
- Consensus rule mismatches against the colleague sheet: {rule_diagnostics["consensus_mismatch_count"]}

The consensus rule is: if any available component assay is `Inactive`, the composite KE call is `0`; otherwise, if at least one available component assay is `Active`, the composite KE call is `1`. This matches the colleague ICE calls better than the current OR rule.

The broad inferred rule:

`KE1_call + KE2_call + KE3_call + (LLNA_call OR LLNA_EC3)`

produces {reverse_candidate_count} ICE candidates and contains all 105 colleague ICE rows. It also produces {reverse_extra_count} extra rows not in the colleague workbook, so there is likely another undocumented filter or extraction difference.
"""
    (output_dir / "reverse_rule_summary.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare colleague complete-case workbook with current derived complete-case CSVs."
    )
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    root = Path.cwd()
    workbook = root / args.workbook
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    colleague_ice = read_colleague_sheet(workbook, COLLEAGUE_ICE_SHEET)
    colleague_skin = read_colleague_sheet(workbook, COLLEAGUE_SKIN_SHEET)
    colleague_ice.to_csv(output_dir / "colleague_ICE_105.csv", index=False)
    colleague_skin.to_csv(output_dir / "colleague_SkinSensDB_209.csv", index=False)

    ice_complete = read_csv(root / OUR_ICE_COMPLETE)
    skin_complete = read_csv(root / OUR_SKIN_COMPLETE)
    ice_full = read_csv(root / OUR_ICE_FULL)
    skin_full = read_csv(root / OUR_SKIN_FULL)

    summary = [
        compare_dataset("ICE", colleague_ice, ice_complete, ice_full, output_dir),
        compare_dataset("SkinSensDB", colleague_skin, skin_complete, skin_full, output_dir),
    ]
    pd.DataFrame(summary).to_csv(output_dir / "comparison_summary.csv", index=False)

    write_ice_colleague_with_our_fields(colleague_ice, ice_full, output_dir)
    rule_diagnostics = write_ice_rule_diagnostics(colleague_ice, ice_full, output_dir)
    reverse_count, reverse_extra_count = write_reverse_rule_outputs(
        ice_full, colleague_ice, output_dir
    )
    write_markdown_summary(output_dir, summary, reverse_count, reverse_extra_count, rule_diagnostics)

    print(pd.DataFrame(summary).to_string(index=False))
    print()
    print("ICE colleague call diagnostics:")
    print(f"Current OR-rule mismatches: {rule_diagnostics['current_or_mismatch_count']}")
    print(f"Consensus-rule mismatches: {rule_diagnostics['consensus_mismatch_count']}")
    print()
    print("ICE reverse candidate rule: KE1_call + KE2_call + KE3_call + (LLNA_call OR LLNA_EC3)")
    print(f"ICE reverse candidate rows: {reverse_count}")
    print(f"ICE reverse candidate not in colleague sheet: {reverse_extra_count}")
    print(f"Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
