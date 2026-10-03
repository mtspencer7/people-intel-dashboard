"""
Produces the numbers quoted in the write-up, as of a given date (default 2026-09-01).
Run:  python analysis/answers.py [--as-of 2026-09-01] [--data data/people_data.xlsx]
Writes analysis/output/answers_<date>.xlsx and prints a summary.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline as p  # noqa: E402

MORGAN, DANA = 12866, 10474


def main(as_of: str, data: str):
    A = pd.Timestamp(as_of)
    d = p.load(data)
    out = {}

    # Q1 -------------------------------------------------------------------
    org = p.org_ids(d, MORGAN)
    q1 = p.roster(d, A, org, ["FTE"])
    out["Q1"] = pd.DataFrame([{
        "leader": "Morgan Reyes (12866)", "fte_headcount_incl_leader": len(q1),
        "fte_headcount_excl_leader": len(q1) - 1,
        "all_workers_incl_contractors_interns": len(p.active_on(d, A, org))}])
    q1_detail = q1.groupby(["director", "dept_name"]).size().rename("fte").reset_index()

    # Q2 -------------------------------------------------------------------
    org2 = p.org_ids(d, DANA)
    q2 = p.roster(d, A, org2, ["FTE"])
    out["Q2"] = pd.DataFrame([{
        "leader": "Dana Whitfield (10474)", "fte_headcount": len(q2),
        "tcc_usd": q2["tcc_usd"].sum(), "base_usd": q2["base_usd"].sum(),
        "target_bonus_usd": q2["bonus_usd"].sum(), "fte_missing_base": int(q2["base_usd"].isna().sum())}])
    q2_detail = q2.groupby(["entity_name", "currency" if "currency" in q2 else "entity_currency"]).agg(
        fte=("employee_id", "size"), tcc_usd=("tcc_usd", "sum")).reset_index()

    # Q3 -------------------------------------------------------------------
    year_start = pd.Timestamp(A.year - 1, 12, 31)
    dates = [year_start] + p.month_ends(f"{A.year}-01-01", A - pd.Timedelta(days=1)) + [A]
    hc = p.headcount_series(d, sorted(set(dates)))
    mv = p.movements(d, f"{A.year}-01-01", A - pd.Timedelta(days=1))
    mv.index = mv.index.astype(str)
    out["Q3_headcount"] = hc
    out["Q3_movements"] = mv.reset_index(names="month")

    # Q4 -------------------------------------------------------------------
    qs = p.quarters_back(A, 9, p.data_start(d))
    out["Q4_voluntary"] = p.attrition(d, qs)
    out["Q4_involuntary"] = p.attrition(d, qs, term_type="Involuntary")
    ttm = [("Prior 12 mo", A - pd.DateOffset(years=2), A - pd.DateOffset(years=1) - pd.Timedelta(days=1)),
           ("Last 12 mo", A - pd.DateOffset(years=1), A - pd.Timedelta(days=1))]
    out["Q4_ttm"] = p.attrition(d, ttm)

    # Q5 -------------------------------------------------------------------
    a = p.attrition(d, qs, tenure="lt1").assign(group="First year (<12 mo)")
    b = p.attrition(d, qs, tenure="ge1").assign(group="12+ months")
    out["Q5_by_quarter"] = pd.concat([a, b])
    out["Q5_ttm"] = pd.concat([p.attrition(d, ttm, tenure="lt1").assign(group="First year"),
                               p.attrition(d, ttm, tenure="ge1").assign(group="12+ months")])
    out["Q5_cohorts"] = p.hire_cohort_retention(d, A).reset_index()
    S, E = ttm[1][1], ttm[1][2]
    for dim in ["vp", "function", "dept_name", "director", "job_level", "location"]:
        out[f"Q5_by_{dim}"] = p.attrition_by(d, dim, S, E, tenure="lt1")

    # Q6 / data quality ------------------------------------------------------
    out["data_issues"] = p.add_asof_issues(d, A)
    out["monthly_summary_recon"] = p.reconcile_monthly_summary(d)

    out_dir = ROOT / "analysis" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"answers_{A:%Y-%m-%d}.xlsx"
    with pd.ExcelWriter(path) as xw:
        for k, v in out.items():
            v.to_excel(xw, sheet_name=k[:31], index=False)
        q1_detail.to_excel(xw, sheet_name="Q1_detail", index=False)
        q2_detail.to_excel(xw, sheet_name="Q2_detail", index=False)

    pct = lambda x: f"{x:.1%}"
    print(f"=== As of {A:%Y-%m-%d} ===")
    print(f"Q1 Morgan Reyes org FTE headcount: {len(q1)} (incl. Morgan); {len(q1)-1} excl.")
    print(f"Q2 Dana Whitfield org FTE TCC: ${q2['tcc_usd'].sum():,.0f} "
          f"(base ${q2['base_usd'].sum():,.0f} + target bonus ${q2['bonus_usd'].sum():,.0f}; {len(q2)} FTEs)")
    print(f"Q3 FTE headcount {hc.iloc[0].headcount} on {hc.iloc[0].date:%Y-%m-%d} -> {hc.iloc[-1].headcount} "
          f"on {hc.iloc[-1].date:%Y-%m-%d} ({hc.iloc[-1].headcount-hc.iloc[0].headcount:+d}); "
          f"hires {mv.hires.sum()}, vol exits {mv.voluntary_exits.sum()}, invol {mv.involuntary_exits.sum()}")
    print(hc.to_string(index=False))
    print(mv.to_string())
    print("Q4 voluntary attrition (annualized):")
    print(out["Q4_voluntary"][["period", "exits", "avg_headcount", "period_rate", "annualized_rate"]].round(4).to_string(index=False))
    print(out["Q4_ttm"][["period", "exits", "avg_headcount", "annualized_rate"]].round(4).to_string(index=False))
    print("Q5 first-year vs 12+ months voluntary (annualized):")
    print(out["Q5_by_quarter"].pivot_table(index="period", columns="group", values="annualized_rate", sort=False).round(3).to_string())
    print(out["Q5_ttm"][["group", "period", "exits", "avg_headcount", "annualized_rate"]].round(3).to_string(index=False))
    print(f"Saved {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-09-01")
    ap.add_argument("--data", default=str(ROOT / "data" / "people_data.xlsx"))
    args = ap.parse_args()
    main(args.as_of, args.data)
