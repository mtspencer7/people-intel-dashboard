"""
Independent re-implementation of Q1-Q5 headline numbers that does NOT import pipeline.py.
Written separately (plain loops / sets, different date parsing) so a bug in the
pipeline would show up as a mismatch. Run: python analysis/verify_independent.py
"""
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 9, 1)


def pdate(v):
    if isinstance(v, datetime):
        return v.date()
    v = str(v).strip()
    if "/" in v:
        m, d_, y = v.split("/")
        return date(int(y), int(m), int(d_))
    return date.fromisoformat(v[:10])


wb = openpyxl.load_workbook(ROOT / "data" / "people_data.xlsx", read_only=True)
rows = lambda s: [r for r in wb[s].iter_rows(values_only=True) if r and r[0] is not None]
emp_rows = rows("employees")
hdr = emp_rows[0]
emps = [dict(zip(hdr, r)) for r in emp_rows[1:]]

# NB: employee_id is zero-padded TEXT in employees/comp_history but a NUMBER in manager_hierarchy -> cast to int.
# de-dup exact rows; drop known duplicate identity 3994 (same email/DOB as 11973, no pay)
seen, stints = set(), []
for e in emps:
    key = tuple(str(v).strip() for v in e.values())
    if key in seen:
        continue
    seen.add(key)
    if int(e["employee_id"]) == 3994:
        continue
    stints.append(dict(id=int(e["employee_id"]), hire=pdate(e["hire_date"]), wt=str(e["worker_type"]).strip(),
                       name=f'{e["first_name"]} {e["last_name"]}', entity=str(e["entity_code"]).strip()))

terms = {}
for r in rows("termination_log")[1:]:
    terms.setdefault(int(r[0]), []).append((pdate(r[1]), r[2]))
for s in stints:  # attach exit to the stint it falls in
    s["term"], s["ttype"] = None, None
    later = [x["hire"] for x in stints if x["id"] == s["id"] and x["hire"] > s["hire"]]
    for td, tt in terms.get(s["id"], []):
        if td >= s["hire"] and (not later or td < min(later)):
            s["term"], s["ttype"] = td, tt


def active(s, d):
    return s["hire"] <= d and (s["term"] is None or s["term"] > d)


kids = {}
for emp, mgr in rows("manager_hierarchy")[1:]:
    if mgr is not None:
        kids.setdefault(int(mgr), set()).add(int(emp))


def org(leader):
    out, todo = {leader}, [leader]
    while todo:
        for k in kids.get(todo.pop(), ()):
            if k not in out:
                out.add(k)
                todo.append(k)
    return out


# Q1
m_org = org(12866)
q1 = sum(1 for s in stints if s["id"] in m_org and s["wt"] == "FTE" and active(s, AS_OF))
print("Q1 Morgan FTE (incl. leader):", q1)

# Q2
fx = {r[3]: r[4] for r in rows("legal_entities")[1:]}
latest = {}
for eid, comp, amt, ccy, basis, eff in rows("comp_history")[1:]:
    eid, eff = int(eid), pdate(eff)
    if eff > AS_OF:
        continue
    k = (eid, comp)
    if k not in latest or eff > latest[k][0]:
        annual = amt * (2080 if basis == "Hourly" else 1)
        latest[k] = (eff, annual * fx[ccy])
d_org = org(10474)
tcc, n = 0.0, 0
for s in stints:
    if s["id"] in d_org and s["wt"] == "FTE" and active(s, AS_OF):
        n += 1
        for comp in ("Base", "Target Bonus"):
            if (s["id"], comp) in latest and latest[(s["id"], comp)][0] >= s["hire"]:
                tcc += latest[(s["id"], comp)][1]
print(f"Q2 Dana FTE TCC: ${tcc:,.2f} across {n} FTEs")

# Q3
for d in [date(2025, 12, 31), date(2026, 6, 30), date(2026, 8, 31), AS_OF]:
    print("Q3 FTE headcount", d, sum(1 for s in stints if s["wt"] == "FTE" and active(s, d)))


# Q4 / Q5: exits / average daily headcount, annualized
def rate(start, end, ttype="Voluntary", tenure=None):
    days = [start + timedelta(i) for i in range((end - start).days + 1)]
    fte = [s for s in stints if s["wt"] == "FTE"]

    def ok_t(s, d):
        t = (d - s["hire"]).days
        return tenure is None or (t < 365 if tenure == "lt1" else t >= 365)
    avg = sum(sum(1 for s in fte if active(s, d) and ok_t(s, d)) for d in days) / len(days)
    ex = [s for s in fte if s["term"] and start <= s["term"] <= end and s["ttype"] == ttype and ok_t(s, s["term"])]
    return len(ex), avg, len(ex) / avg * 365 / len(days)


for lab, a, b in [("2024 Q4", date(2024, 10, 1), date(2024, 12, 31)), ("2025 Q4", date(2025, 10, 1), date(2025, 12, 31)),
                  ("2026 Q2", date(2026, 4, 1), date(2026, 6, 30)), ("2026 Q3 to date", date(2026, 7, 1), date(2026, 8, 31))]:
    n, avg, r = rate(a, b)
    print(f"Q4 {lab}: {n} vol exits, avg HC {avg:.1f}, annualized {r:.2%}")
for ten in ("lt1", "ge1"):
    n, avg, r = rate(date(2025, 9, 1), date(2026, 8, 31), tenure=ten)
    n0, avg0, r0 = rate(date(2024, 9, 1), date(2025, 8, 31), tenure=ten)
    print(f"Q5 {ten}: last 12m {n} exits / {avg:.1f} = {r:.2%}; prior 12m {n0} / {avg0:.1f} = {r0:.2%}")
