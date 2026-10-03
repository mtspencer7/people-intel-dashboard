"""
People Intelligence pipeline: load -> clean -> validate -> metrics.

Single source of truth used by both the Streamlit app (app.py) and the
answer script (analysis/answers.py). Every metric takes an `as_of` date so the
same code answers "as of Sep 1, 2026" today and "as of Oct 1, 2026" next month.

Key conventions (also documented in the write-up):
  * One row per employment *stint*. An employee_id that appears twice with
    different hire dates is a rehire (two stints), not a duplicate.
  * Active on date D  <=>  hire_date <= D  and  (no termination  or  termination_date > D).
    (A termination dated D means the person is not counted in D's headcount;
    this matches how the team's monthly_summary sheet has been counting.)
  * termination_log is the system of record for exits. If employment_status
    disagrees with it, the log wins and the record is flagged.
  * Org = leader + everyone below them in manager_hierarchy (current lines;
    leavers are attributed to the last manager on file).
  * TCC (annualized, USD) = annual base (hourly x 2,080) + annual target bonus,
    using the latest record effective on/before the as-of date, converted at
    the fx_rate_to_usd in legal_entities for the record's currency.
  * Attrition rate = exits / average daily headcount over the period;
    "annualized" scales by 365 / days in period.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

HOURS_PER_YEAR = 2080
FIRST_YEAR_DAYS = 365
SHEETS = [
    "employees", "manager_hierarchy", "departments", "legal_entities",
    "comp_history", "termination_log", "monthly_summary",
]


# --------------------------------------------------------------------------- #
# Data container
# --------------------------------------------------------------------------- #
@dataclass
class PeopleData:
    stints: pd.DataFrame          # one row per employment stint, cleaned + enriched
    hierarchy: pd.DataFrame       # employee_id -> manager_employee_id
    departments: pd.DataFrame
    entities: pd.DataFrame
    comp: pd.DataFrame            # cleaned, with annual_usd
    terms: pd.DataFrame           # cleaned, matched to stints
    monthly_summary: pd.DataFrame
    issues: pd.DataFrame          # data-quality log
    children: dict = field(default_factory=dict)  # manager -> [direct reports]

    # ---- people lookups -------------------------------------------------- #
    def person_label(self, emp_id: int) -> str:
        row = self.latest_stint().loc[emp_id]
        return f"{row.first_name} {row.last_name}"

    def latest_stint(self) -> pd.DataFrame:
        return (self.stints.sort_values("hire_date")
                .drop_duplicates("employee_id", keep="last")
                .set_index("employee_id"))


# --------------------------------------------------------------------------- #
# Loading & cleaning
# --------------------------------------------------------------------------- #
def _strip(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            df[c] = df[c].astype(str).str.strip()
    return df


def _parse_dates(s: pd.Series) -> pd.Series:
    """Accepts ISO (YYYY-MM-DD) and US (M/D/YYYY). Anything else -> NaT (flagged)."""
    s = s.astype(str).str.strip()
    iso = pd.to_datetime(s.where(s.str.match(r"^\d{4}-\d{2}-\d{2}")), format="%Y-%m-%d", errors="coerce")
    us = pd.to_datetime(s.where(s.str.match(r"^\d{1,2}/\d{1,2}/\d{4}$")), format="%m/%d/%Y", errors="coerce")
    return iso.fillna(us)


def load(source) -> PeopleData:
    """`source` is a path or a file-like object (e.g. a Streamlit upload)."""
    raw = pd.read_excel(source, sheet_name=None, dtype={"employee_id": str, "manager_employee_id": str})
    missing = [s for s in SHEETS if s not in raw]
    if missing:
        raise ValueError(f"Workbook is missing sheet(s): {', '.join(missing)}")

    issues: list[dict] = []
    # employee_id arrives as zero-padded text ('02321') in some sheets and as a number in others.
    id_cols = {"employees": ["employee_id"], "manager_hierarchy": ["employee_id", "manager_employee_id"],
               "comp_history": ["employee_id"], "termination_log": ["employee_id"]}
    id_types = {}
    for sh, cols in id_cols.items():
        for col in cols:
            s = raw[sh][col]
            id_types[(sh, col)] = "zero-padded text" if s.dropna().astype(str).str.match(r"^0\d+$").any() else "number"
            raw[sh][col] = pd.to_numeric(s.astype(str).str.strip().replace({"nan": None, "None": None, "": None}),
                                         errors="coerce").astype("Int64")

    def log(check, severity, n, handling, ids=None, detail=""):
        if n:
            ids = list(dict.fromkeys(int(i) for i in (ids if ids is not None else [])))
            issues.append(dict(check=check, severity=severity, records=int(n),
                               detail=detail, handling=handling,
                               example_ids=", ".join(map(str, ids[:8]))))

    kinds = set(id_types.values())
    if len(kinds) > 1:
        txt = sorted({sh for (sh, _), k in id_types.items() if k != "number"})
        num = sorted({sh for (sh, _), k in id_types.items() if k == "number"})
        log("employee_id stored as text in some sheets, numbers in others", "High",
            int(raw["employees"]["employee_id"].notna().sum()),
            "Cast every ID to an integer before joining. In Excel, a VLOOKUP of '02321' against 2321 fails silently.",
            detail=f"Zero-padded text in: {', '.join(txt)}; numeric in: {', '.join(num)}")

    # ---- reference tables ------------------------------------------------ #
    depts = _strip(raw["departments"])
    depts["dept_code"] = depts["dept_code"].str.upper()
    ents = _strip(raw["legal_entities"])
    fx = ents.drop_duplicates("currency").set_index("currency")["fx_rate_to_usd"].to_dict()

    # ---- employees ------------------------------------------------------- #
    e0 = raw["employees"]
    e = _strip(e0)
    n_status = (e["employment_status"] != e["employment_status"].str.title()).sum()
    e["employment_status"] = e["employment_status"].str.title()
    log("Inconsistent status casing (e.g. 'ACTIVE')", "Low", n_status, "Normalized to Title case.",
        e.loc[e0["employment_status"].astype(str) != e0["employment_status"].astype(str).str.title(), "employee_id"])
    bad_dept = e["dept_code"] != e["dept_code"].str.upper()
    log("Lower-case department codes (e.g. 'd10')", "Medium", bad_dept.sum(),
        "Upper-cased before joining to departments; otherwise these people drop out of dept views.",
        e.loc[bad_dept, "employee_id"])
    e["dept_code"] = e["dept_code"].str.upper()
    ws_loc = e0["location"].astype(str) != e0["location"].astype(str).str.strip()
    log("Trailing spaces in location", "Low", ws_loc.sum(), "Trimmed (otherwise 'Denver, CO' splits into two values).",
        e0.loc[ws_loc, "employee_id"])
    hd_raw = e0["hire_date"].astype(str)
    nonstd = ~hd_raw.str.match(r"^\d{4}-\d{2}-\d{2}$")
    log("Hire dates in mixed formats (ISO, M/D/YYYY, padded)", "Medium", nonstd.sum(),
        "Parsed both formats explicitly. Slash dates are M/D/YYYY (day > 12 appears only in the 2nd position).",
        e0.loc[nonstd, "employee_id"])
    e["hire_date"] = _parse_dates(e["hire_date"])
    e["date_of_birth"] = _parse_dates(e["date_of_birth"])
    log("Unparseable hire date", "High", e["hire_date"].isna().sum(), "Row excluded from metrics.",
        e.loc[e["hire_date"].isna(), "employee_id"])

    dup_mask = e.duplicated(keep="first")
    log("Exact duplicate employee rows", "High", dup_mask.sum(),
        "Dropped the copy (would otherwise double-count headcount and comp).", e.loc[dup_mask, "employee_id"])
    e = e[~dup_mask & e["hire_date"].notna()].copy()

    rehire = e[e["employee_id"].duplicated(keep=False)]
    log("Same employee_id on two rows with different hire dates", "Medium", rehire["employee_id"].nunique(),
        "Treated as a rehire: two separate employment stints under one ID.", rehire["employee_id"])

    # Same person under two employee_ids: same email + DOB + last name.
    # Keep the ID that has compensation history (the real payroll record); drop the other.
    comp_ids = set(raw["comp_history"]["employee_id"])
    one = e.drop_duplicates("employee_id").copy()
    one["_key"] = one["email"].str.lower() + "|" + one["date_of_birth"].astype(str) + "|" + one["last_name"].str.lower()
    grp = one[one["_key"].duplicated(keep=False)]
    drop_ids, detail = [], []
    for _, g in grp.groupby("_key"):
        g = g.assign(_has_comp=g["employee_id"].isin(comp_ids)).sort_values(["_has_comp", "hire_date"],
                                                                            ascending=[False, True])
        keep = g.iloc[0]
        for r in g.iloc[1:].itertuples():
            drop_ids.append(r.employee_id)
            detail.append(f"{r.employee_id} '{r.first_name} {r.last_name}' duplicates "
                          f"{keep.employee_id} '{keep.first_name} {keep.last_name}' (same email, DOB, dept; no pay record)")
    log("Same person under two employee IDs", "High", len(drop_ids),
        "Dropped the ID with no comp history. After this fix, rebuilt headcount matches the "
        "team's monthly_summary exactly in every month.", drop_ids, detail="; ".join(detail))
    e = e[~e["employee_id"].isin(drop_ids)].copy()
    dup_email = e.drop_duplicates("employee_id")
    dup_email = dup_email[dup_email["email"].str.lower().duplicated(keep=False)]
    log("Different employees sharing one email address", "Medium", len(dup_email),
        "Kept both people (different IDs). Email is not a safe join key.", dup_email["employee_id"],
        detail="; ".join(f"{r.employee_id}: {r.first_name} {r.last_name}" for r in dup_email.itertuples()))

    age_at_hire = (e["hire_date"] - e["date_of_birth"]).dt.days / 365.25
    young = age_at_hire < 16
    log("Implausible date of birth (under 16 at hire)", "Low", young.sum(),
        "Not used in any metric; flagged for HRIS correction.", e.loc[young, "employee_id"])

    e = e.sort_values(["employee_id", "hire_date"]).reset_index(drop=True)
    e["stint"] = e.groupby("employee_id").cumcount() + 1
    e["next_hire"] = e.groupby("employee_id")["hire_date"].shift(-1)
    e["stint_id"] = e["employee_id"].astype(str) + "-" + e["stint"].astype(str)

    # ---- terminations ---------------------------------------------------- #
    t = _strip(raw["termination_log"])
    t["termination_date"] = _parse_dates(t["termination_date"])
    t["termination_type"] = t["termination_type"].str.title()
    # match each termination to the stint it ends
    cand = t.merge(e[["employee_id", "stint_id", "hire_date", "next_hire"]], on="employee_id", how="left")
    ok = (cand["termination_date"] >= cand["hire_date"]) & (
        cand["next_hire"].isna() | (cand["termination_date"] < cand["next_hire"]))
    matched = cand[ok]
    t_m = t.reset_index().merge(matched[["employee_id", "termination_date", "stint_id"]],
                                on=["employee_id", "termination_date"], how="left")
    unmatched = t_m[t_m["stint_id"].isna()]
    log("Termination dated before the employee's hire date", "High", len(unmatched),
        "Excluded from metrics (cannot belong to any stint).", unmatched["employee_id"])

    e = e.merge(t_m.dropna(subset=["stint_id"])[["stint_id", "termination_date", "termination_type", "reason"]],
                on="stint_id", how="left")

    # status vs. termination log
    mism_active = (e["employment_status"] == "Active") & e["termination_date"].notna()
    log("Status 'Active' but termination_log has an exit", "High", mism_active.sum(),
        "Termination log treated as system of record -> counted as terminated on that date.",
        e.loc[mism_active, "employee_id"],
        detail="; ".join(f"{r.employee_id} exited {r.termination_date:%Y-%m-%d} ({r.reason})"
                         for r in e[mism_active].itertuples()))
    mism_term = (e["employment_status"] == "Terminated") & e["termination_date"].isna()
    log("Status 'Terminated' but no termination record", "High", mism_term.sum(),
        "No exit date -> cannot be placed in time; excluded from headcount after hire.",
        e.loc[mism_term, "employee_id"])
    # rehire row whose ID's earlier exit makes status ambiguous -> nothing to do, logged above

    # misclassified reasons
    eoi = (e["reason"] == "End of Internship") & (e["termination_type"] == "Voluntary")
    log("'End of Internship' coded as Voluntary", "Medium", eoi.sum(),
        "Interns are excluded from FTE attrition, so no impact on FTE rates; would inflate an all-worker voluntary rate.",
        e.loc[eoi, "employee_id"])

    # ---- enrich ---------------------------------------------------------- #
    e = e.merge(depts, on="dept_code", how="left")
    log("Department code not in departments table", "Medium", e["dept_name"].isna().sum(),
        "Shown as 'Unknown'.", e.loc[e["dept_name"].isna(), "employee_id"])
    e["dept_name"] = e["dept_name"].fillna("Unknown")
    e["function"] = e["function"].fillna("Unknown")
    e = e.merge(ents[["entity_code", "entity_name", "country", "currency"]].rename(
        columns={"currency": "entity_currency"}), on="entity_code", how="left")
    e["full_name"] = e["first_name"] + " " + e["last_name"]
    e["is_fte"] = e["worker_type"].eq("FTE")

    common_hire = e["hire_date"].value_counts()
    top_date, top_n = common_hire.index[0], common_hire.iloc[0]
    if top_n > 3 * max(common_hire.iloc[1:6].mean(), 1):
        log(f"Hire-date spike on {top_date:%Y-%m-%d}", "Low", int(top_n),
            "Likely an HRIS go-live/migration default, i.e. true start dates are earlier. "
            "Only affects tenure for long-tenured staff; no impact on first-year metrics.",
            e.loc[e["hire_date"] == top_date, "employee_id"])

    # ---- hierarchy ------------------------------------------------------- #
    h = raw["manager_hierarchy"].drop_duplicates("employee_id").copy()
    h["manager_employee_id"] = h["manager_employee_id"].astype("Int64")
    orphan = ~h["manager_employee_id"].isna() & ~h["manager_employee_id"].isin(e["employee_id"])
    log("Manager ID not found in roster", "High", orphan.sum(), "Treated as top of its own tree.",
        h.loc[orphan, "employee_id"])
    no_mgr_row = ~e["employee_id"].isin(h["employee_id"])
    log("Employee missing from manager_hierarchy", "Medium", no_mgr_row.sum(),
        "Cannot be placed in any leader's org (still in company totals).", e.loc[no_mgr_row, "employee_id"])
    children: dict[int, list[int]] = {}
    for emp, mgr in zip(h["employee_id"], h["manager_employee_id"]):
        if pd.notna(mgr):
            children.setdefault(int(mgr), []).append(int(emp))
    e = e.merge(h, on="employee_id", how="left")

    # Leaders above each person (Director / VP), resolved by walking up the tree.
    parent = {int(k): (int(v) if pd.notna(v) else None) for k, v in zip(h["employee_id"], h["manager_employee_id"])}
    lvl = e.drop_duplicates("employee_id", keep="last").set_index("employee_id")["job_level"].to_dict()
    nm = e.drop_duplicates("employee_id", keep="last").set_index("employee_id")["full_name"].to_dict()
    cycles = []

    def ancestor(emp, level):
        seen, cur = set(), int(emp)
        while cur is not None:
            if cur in seen:
                cycles.append(emp)
                return None
            seen.add(cur)
            if lvl.get(cur) == level:
                return cur
            cur = parent.get(cur)
        return None

    for level, col in [("Director", "director"), ("VP", "vp")]:
        e[col] = [f"{nm[i]} ({i})" if i is not None else "—"
                  for i in (ancestor(x, level) for x in e["employee_id"])]
    log("Reporting-line loop in manager_hierarchy", "High", len(set(cycles)),
        "Loop broken; affected people roll up to no leader.", cycles)
    term_mgr_lvl = e.loc[e["termination_date"].notna(), "manager_employee_id"].map(lvl)
    n_skip = int((term_mgr_lvl == "Director").sum())
    if n_skip and n_skip > 0.8 * term_mgr_lvl.notna().sum():
        log("Leavers re-pointed to a Director in manager_hierarchy", "Medium", n_skip,
            "Every active IC reports to a Manager, but leavers report to the Director above. "
            "Org roll-ups for Directors/VPs are unaffected; attrition by front-line manager "
            "cannot be measured from this file (Director is the lowest reliable level).",
            e.loc[e["termination_date"].notna(), "employee_id"])

    # ---- compensation ---------------------------------------------------- #
    c = _strip(raw["comp_history"])
    c["effective_date"] = _parse_dates(c["effective_date"])
    c["fx"] = c["currency"].map(fx)
    log("Comp record in a currency with no FX rate", "High", c["fx"].isna().sum(), "Excluded from TCC.",
        c.loc[c["fx"].isna(), "employee_id"])
    c["annual_local"] = np.where(c["pay_basis"].eq("Hourly"), c["amount"] * HOURS_PER_YEAR, c["amount"])
    c["annual_usd"] = c["annual_local"] * c["fx"]
    ent_ccy = e.drop_duplicates("employee_id", keep="last").set_index("employee_id")["entity_currency"]
    ccy_mis = c["currency"] != c["employee_id"].map(ent_ccy)
    one_e = e.drop_duplicates("employee_id", keep="last").set_index("employee_id")
    mis_ids = c.loc[ccy_mis, "employee_id"]
    wts = mis_ids.map(one_e["worker_type"]).value_counts().to_dict()
    log("Pay currency differs from employing entity's currency", "Medium", ccy_mis.sum(),
        "Converted using the currency on the comp record (as stated). "
        + ("No effect on FTE TCC (none are FTEs). " if "FTE" not in wts else "")
        + "Confirm with Payroll whether these should be local currency.", mis_ids,
        detail=", ".join(f"{v} {k}" for k, v in wts.items()) + " in "
               + ", ".join(sorted(mis_ids.map(one_e["entity_name"]).dropna().unique())))
    # Future-dated rows are scheduled changes; comp_as_of() ignores them until effective
    # (reported per as-of date by add_asof_issues).
    # stints with no base on file
    base_ids = set(c.loc[c["component"] == "Base", "employee_id"])
    nobase = e["is_fte"] & e["termination_date"].isna() & ~e["employee_id"].isin(base_ids)
    log("Active FTE with no base pay record", "High", nobase.sum(),
        "Counted in headcount; contributes $0 to TCC (understates TCC). Needs Payroll follow-up.",
        e.loc[nobase, "employee_id"])

    # ---- monthly summary ------------------------------------------------- #
    ms = raw["monthly_summary"].copy()
    ms["month_end"] = _parse_dates(ms["month_end"])

    issues_df = pd.DataFrame(issues, columns=["check", "severity", "records", "detail", "handling", "example_ids"])
    sev_order = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
    issues_df = issues_df.sort_values("severity", key=lambda s: s.map(sev_order)).reset_index(drop=True)

    return PeopleData(stints=e, hierarchy=h, departments=depts, entities=ents, comp=c,
                      terms=t_m, monthly_summary=ms, issues=issues_df, children=children)


def add_asof_issues(d: PeopleData, as_of) -> pd.DataFrame:
    """Issues that depend on the as-of date (e.g. scheduled comp changes)."""
    as_of = pd.Timestamp(as_of)
    rows = []
    fut = d.comp[d.comp["effective_date"] > as_of]
    if len(fut):
        rows.append(dict(check="Comp changes effective after the as-of date", severity="Info",
                         records=len(fut),
                         detail=", ".join(f"{k:%Y-%m-%d}: {v}" for k, v in fut["effective_date"].value_counts().items()),
                         handling="Ignored for this as-of date; picked up automatically once effective.",
                         example_ids=", ".join(map(str, fut["employee_id"].head(8)))))
    future_hire = d.stints[d.stints["hire_date"] > as_of]
    if len(future_hire):
        rows.append(dict(check="Hires dated after the as-of date", severity="Info", records=len(future_hire),
                         detail="", handling="Not counted until their start date.",
                         example_ids=", ".join(map(str, future_hire["employee_id"].head(8)))))
    return pd.concat([d.issues, pd.DataFrame(rows)], ignore_index=True) if rows else d.issues


# --------------------------------------------------------------------------- #
# Org helpers
# --------------------------------------------------------------------------- #
def org_ids(d: PeopleData, leader_id: int | None, include_leader: bool = True) -> set[int] | None:
    """All employee_ids in leader's org (recursive). None = whole company."""
    if leader_id is None:
        return None
    seen, stack = set(), [int(leader_id)]
    while stack:
        m = stack.pop()
        for r in d.children.get(m, []):
            if r not in seen:
                seen.add(r)
                stack.append(r)
    if include_leader:
        seen.add(int(leader_id))
    return seen


def leaders(d: PeopleData, as_of) -> pd.DataFrame:
    """People with at least one report who are active on as_of, for the leader picker."""
    act = active_on(d, as_of)
    act = act[act["employee_id"].isin(d.children.keys())].copy()
    act["org_size"] = [len(org_ids(d, i, include_leader=False) & set(active_on(d, as_of)["employee_id"]))
                       for i in act["employee_id"]]
    lvl = {"CEO": 0, "VP": 1, "Director": 2, "Manager": 3}
    act["lvl"] = act["job_level"].map(lvl).fillna(9)
    act = act.sort_values(["lvl", "org_size"], ascending=[True, False])
    act["label"] = (act["full_name"] + " — " + act["job_level"] + ", " + act["dept_name"]
                    + " (" + act["org_size"].astype(str) + " in org)")
    return act[["employee_id", "full_name", "job_level", "dept_name", "org_size", "label"]]


def _filter(df: pd.DataFrame, org: set[int] | None, worker_types: Iterable[str] | None) -> pd.DataFrame:
    if org is not None:
        df = df[df["employee_id"].isin(org)]
    if worker_types is not None:
        df = df[df["worker_type"].isin(list(worker_types))]
    return df


# --------------------------------------------------------------------------- #
# Point-in-time metrics
# --------------------------------------------------------------------------- #
def active_on(d: PeopleData, as_of, org: set[int] | None = None,
              worker_types: Iterable[str] | None = None) -> pd.DataFrame:
    as_of = pd.Timestamp(as_of)
    s = _filter(d.stints, org, worker_types)
    m = (s["hire_date"] <= as_of) & (s["termination_date"].isna() | (s["termination_date"] > as_of))
    out = s[m].copy()
    out["tenure_days"] = (as_of - out["hire_date"]).dt.days
    return out


def comp_as_of(d: PeopleData, as_of) -> pd.DataFrame:
    """Latest Base and Target Bonus per employee effective on/before as_of (annual USD)."""
    as_of = pd.Timestamp(as_of)
    c = d.comp[d.comp["effective_date"] <= as_of].sort_values("effective_date")
    latest = c.drop_duplicates(["employee_id", "component"], keep="last")
    p = latest.pivot(index="employee_id", columns="component", values="annual_usd")
    p = p.rename(columns={"Base": "base_usd", "Target Bonus": "bonus_usd"})
    for col in ["base_usd", "bonus_usd"]:
        if col not in p:
            p[col] = np.nan
    eff = latest[latest["component"] == "Base"].set_index("employee_id")["effective_date"]
    p["base_effective"] = eff
    return p


def roster(d: PeopleData, as_of, org=None, worker_types=None) -> pd.DataFrame:
    a = active_on(d, as_of, org, worker_types)
    a = a.merge(comp_as_of(d, as_of), left_on="employee_id", right_index=True, how="left")
    # comp must belong to the current stint (rehires)
    stale = a["base_effective"].notna() & (a["base_effective"] < a["hire_date"])
    a.loc[stale, ["base_usd", "bonus_usd"]] = np.nan
    a["tcc_usd"] = a["base_usd"].fillna(0) + a["bonus_usd"].fillna(0)
    a.loc[~a["is_fte"], "tcc_usd"] = a.loc[~a["is_fte"], "tcc_usd"].where(a["base_usd"].notna())
    return a


# --------------------------------------------------------------------------- #
# Time-series metrics
# --------------------------------------------------------------------------- #
def month_ends(start, end) -> list[pd.Timestamp]:
    return list(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="ME"))


def headcount_series(d: PeopleData, dates, org=None, worker_types=("FTE",)) -> pd.DataFrame:
    s = _filter(d.stints, org, worker_types)
    rows = []
    for dt in dates:
        dt = pd.Timestamp(dt)
        act = (s["hire_date"] <= dt) & (s["termination_date"].isna() | (s["termination_date"] > dt))
        lt1 = act & ((dt - s["hire_date"]).dt.days < FIRST_YEAR_DAYS)
        rows.append(dict(date=dt, headcount=int(act.sum()), first_year=int(lt1.sum())))
    return pd.DataFrame(rows)


def movements(d: PeopleData, start, end, org=None, worker_types=("FTE",), freq="ME") -> pd.DataFrame:
    """Hires and exits per period (start exclusive of nothing: start <= date <= end)."""
    s = _filter(d.stints, org, worker_types)
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    hires = s[(s["hire_date"] >= start) & (s["hire_date"] <= end)]
    exits = s[(s["termination_date"] >= start) & (s["termination_date"] <= end)]
    per = lambda x: x.dt.to_period("M" if freq == "ME" else "Q")
    out = pd.DataFrame({
        "hires": hires.groupby(per(hires["hire_date"])).size(),
        "voluntary_exits": exits[exits["termination_type"] == "Voluntary"].groupby(per(exits["termination_date"])).size(),
        "involuntary_exits": exits[exits["termination_type"] == "Involuntary"].groupby(per(exits["termination_date"])).size(),
    }).fillna(0).astype(int)
    idx = pd.period_range(start, end, freq="M" if freq == "ME" else "Q")
    return out.reindex(idx, fill_value=0)


def _daily_headcount(s: pd.DataFrame, days: pd.DatetimeIndex, tenure: str | None = None) -> np.ndarray:
    """Headcount on each day (vectorised). tenure: None | 'lt1' | 'ge1'."""
    hd = s["hire_date"].values[:, None]
    td = s["termination_date"].values[:, None]
    dv = days.values[None, :]
    act = (hd <= dv) & (pd.isna(s["termination_date"]).values[:, None] | (td > dv))
    if tenure:
        ten = (dv - hd).astype("timedelta64[D]").astype(int)
        act &= (ten < FIRST_YEAR_DAYS) if tenure == "lt1" else (ten >= FIRST_YEAR_DAYS)
    return act.sum(axis=0)


def attrition(d: PeopleData, periods: list[tuple], org=None, worker_types=("FTE",),
              term_type: str | None = "Voluntary", tenure: str | None = None) -> pd.DataFrame:
    """
    periods: list of (label, start, end) inclusive.
    tenure: None (everyone), 'lt1' (exits & headcount with < 1 yr tenure), 'ge1'.
    Returns exits, avg daily headcount, period rate and annualized rate.
    """
    s = _filter(d.stints, org, worker_types)
    ds = data_start(d)
    rows = []
    for label, start, end in periods:
        start, end = max(pd.Timestamp(start), ds), pd.Timestamp(end)
        if end < start:  # entirely before exits were tracked -> unknowable
            rows.append(dict(period=label, start=start, end=end, days=0, exits=0, avg_headcount=np.nan,
                             period_rate=np.nan, annualized_rate=np.nan))
            continue
        days = pd.date_range(start, end, freq="D")
        avg_hc = _daily_headcount(s, days, tenure).mean() if len(s) else 0.0
        ex = s[(s["termination_date"] >= start) & (s["termination_date"] <= end)]
        if term_type:
            ex = ex[ex["termination_type"] == term_type]
        ten_at_exit = (ex["termination_date"] - ex["hire_date"]).dt.days
        if tenure == "lt1":
            ex = ex[ten_at_exit < FIRST_YEAR_DAYS]
        elif tenure == "ge1":
            ex = ex[ten_at_exit >= FIRST_YEAR_DAYS]
        n = len(ex)
        rate = n / avg_hc if avg_hc else np.nan
        rows.append(dict(period=label, start=start, end=end, days=len(days), exits=n,
                         avg_headcount=avg_hc, period_rate=rate,
                         annualized_rate=rate * 365 / len(days) if avg_hc else np.nan))
    return pd.DataFrame(rows)


def attrition_by(d: PeopleData, dim: str, start, end, org=None, worker_types=("FTE",),
                 term_type: str | None = "Voluntary", tenure: str | None = None,
                 min_headcount: float = 0) -> pd.DataFrame:
    """Annualized attrition for each value of `dim` (a stints column, e.g. dept_name, job_level,
    manager_name) over [start, end]."""
    s = _filter(d.stints, org, worker_types)
    if dim == "manager_name":
        names = d.latest_stint()["full_name"]
        s = s.assign(manager_name=s["manager_employee_id"].map(
            lambda m: f"{names.get(m, '?')} ({int(m)})" if pd.notna(m) else "—"))
    start, end = max(pd.Timestamp(start), data_start(d)), pd.Timestamp(end)
    if end < start:
        return pd.DataFrame(columns=[dim, "exits", "avg_headcount", "annualized_rate"])
    days = pd.date_range(start, end, freq="D")
    rows = []
    for val, g in s.groupby(dim):
        avg = _daily_headcount(g, days, tenure).mean()
        ex = g[(g["termination_date"] >= start) & (g["termination_date"] <= end)]
        if term_type:
            ex = ex[ex["termination_type"] == term_type]
        ten = (ex["termination_date"] - ex["hire_date"]).dt.days
        if tenure == "lt1":
            ex = ex[ten < FIRST_YEAR_DAYS]
        elif tenure == "ge1":
            ex = ex[ten >= FIRST_YEAR_DAYS]
        rows.append({dim: val, "exits": len(ex), "avg_headcount": avg,
                     "annualized_rate": (len(ex) / avg * 365 / len(days)) if avg else np.nan})
    out = pd.DataFrame(rows)
    out = out[out["avg_headcount"] >= min_headcount]
    return out.sort_values("annualized_rate", ascending=False).reset_index(drop=True)


def hire_cohort_retention(d: PeopleData, as_of, org=None, worker_types=("FTE",), freq="Q") -> pd.DataFrame:
    """For each hire cohort: hires, voluntary/any exits within 365 days, and whether the cohort has a full
    12 months of observation by as_of. Cohorts hired before exits were tracked are excluded."""
    as_of = pd.Timestamp(as_of)
    s = _filter(d.stints, org, worker_types)
    s = s[s["hire_date"] >= data_start(d)].copy()
    s["cohort"] = s["hire_date"].dt.to_period(freq)
    ten = (s["termination_date"] - s["hire_date"]).dt.days
    s["left_fy"] = s["termination_date"].notna() & (ten < FIRST_YEAR_DAYS) & (s["termination_date"] < as_of)
    s["left_fy_vol"] = s["left_fy"] & s["termination_type"].eq("Voluntary")
    s["left_90"] = s["termination_date"].notna() & (ten < 90) & (s["termination_date"] < as_of)
    g = s.groupby("cohort").agg(hires=("stint_id", "size"), left_within_1yr=("left_fy", "sum"),
                                vol_within_1yr=("left_fy_vol", "sum"), left_within_90d=("left_90", "sum"),
                                last_hire=("hire_date", "max"))
    g["full_year_observed"] = (g["last_hire"] + pd.Timedelta(days=FIRST_YEAR_DAYS)) <= as_of
    g["pct_left_1yr"] = g["left_within_1yr"] / g["hires"]
    g["pct_vol_1yr"] = g["vol_within_1yr"] / g["hires"]
    g["pct_left_90d"] = g["left_within_90d"] / g["hires"]
    g.index = g.index.astype(str)
    return g.drop(columns="last_hire")


def quarters_back(as_of, n: int = 8, data_start=None) -> list[tuple]:
    """Last n calendar quarters ending at as_of. The current quarter is partial (through the day before as_of
    if as_of is the 1st of a month, i.e. through the last complete month)."""
    as_of = pd.Timestamp(as_of)
    last_day = as_of - pd.Timedelta(days=1) if as_of.day == 1 else as_of
    q = last_day.to_period("Q")
    out = []
    for i in range(n - 1, -1, -1):
        p = q - i
        start, end = p.start_time.normalize(), min(p.end_time.normalize(), last_day)
        partial = end < p.end_time.normalize()
        if data_start is not None and start < pd.Timestamp(data_start):
            if end < pd.Timestamp(data_start):
                continue
            start, partial = pd.Timestamp(data_start), True
        label = f"{p.year} Q{p.quarter}" + (" (partial)" if partial else "")
        out.append((label, start, end))
    return out


def reconcile_monthly_summary(d: PeopleData) -> pd.DataFrame:
    ms = d.monthly_summary.copy()
    hc = headcount_series(d, ms["month_end"])
    mv = movements(d, ms["month_end"].min().replace(day=1), ms["month_end"].max())
    ms["calc_fte_headcount"] = hc["headcount"].values
    ms["calc_first_year"] = hc["first_year"].values
    per = ms["month_end"].dt.to_period("M")
    ms["calc_voluntary"] = per.map(mv["voluntary_exits"]).values
    ms["calc_involuntary"] = per.map(mv["involuntary_exits"]).values
    ms["diff_headcount"] = ms["fte_headcount"] - ms["calc_fte_headcount"]
    ms["diff_first_year"] = ms["fte_headcount_tenure_lt_1yr"] - ms["calc_first_year"]
    ms["diff_voluntary"] = ms["voluntary_terms"] - ms["calc_voluntary"]
    ms["diff_involuntary"] = ms["involuntary_terms"] - ms["calc_involuntary"]
    return ms


def data_start(d: PeopleData) -> pd.Timestamp:
    """First date for which exits are recorded; attrition before this is unknowable."""
    return d.terms["termination_date"].min()
