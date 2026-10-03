"""
People Intelligence — HRBP Self-Serve Dashboard
Run locally:  streamlit run app.py
All logic lives in pipeline.py; this file is presentation only.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import pipeline as p

ROOT = Path(__file__).parent
def find_default_data() -> Path | None:
    """Look for the on-record workbook in data/ first, then the repo root (any *people_data*.xlsx)."""
    for folder in (ROOT / "data", ROOT):
        exact = folder / "people_data.xlsx"
        if exact.exists():
            return exact
        hits = sorted(folder.glob("*people_data*.xlsx"))
        if hits:
            return hits[0]
    return None


DEFAULT_DATA = find_default_data()

# Palette (validated categorical slots; see write-up). Text never wears series colour.
BLUE, ORANGE, GRAY, LIGHTGRAY = "#2a78d6", "#eb6834", "#8a8984", "#d9d8d4"
INK, INK2 = "#1f1f1e", "#52514e"

st.set_page_config(page_title="People Intelligence | HRBP Dashboard", page_icon="📊", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px;}
  [data-testid="stMetricValue"] {font-size: 1.75rem;}
  [data-testid="stMetricLabel"] p {font-size: .85rem; color: #52514e;}
  .answer {border-left: 4px solid #2a78d6; padding: .55rem .9rem; margin: .35rem 0 .9rem;
           background: rgba(42,120,214,.06); border-radius: 4px;}
  .answer b.q {display:block; font-size:.8rem; color:#52514e; font-weight:600; text-transform:uppercase;
               letter-spacing:.03em; margin-bottom:.15rem;}
  .note {color:#52514e; font-size:.85rem;}
  div[data-testid="stTabs"] button p {font-size: .95rem;}
</style>""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Data loading (cached by file content, so a new upload refreshes everything)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="Cleaning and validating the workbook…")
def load_cached(digest: str, raw: bytes) -> p.PeopleData:
    return p.load(io.BytesIO(raw))


def default_as_of(d: p.PeopleData) -> pd.Timestamp:
    """First day of the month after the latest recorded event (hire or exit)."""
    last = max(d.stints["hire_date"].max(), d.stints["termination_date"].max())
    return (last + pd.offsets.MonthBegin(1)).normalize()


with st.sidebar:
    st.markdown("### 📊 People Intelligence")
    st.caption("Self-serve answers for HR Business Partners")
    up = st.file_uploader("Data file (optional)", type=["xlsx"],
                          help="Leave empty to use the latest file on record. To refresh, upload this month's "
                               "people_data.xlsx export. It must have the same 7 sheets.")
    if up is None and DEFAULT_DATA is None:
        st.info("No data file on record yet. Upload this month's **people_data.xlsx** above to get started.")
        st.stop()
    raw = up.getvalue() if up else DEFAULT_DATA.read_bytes()
    try:
        d = load_cached(hashlib.md5(raw).hexdigest(), raw)
    except Exception as ex:  # friendly error instead of a stack trace
        st.error(f"Couldn't read that file: {ex}")
        st.stop()
    st.caption(f"Using: **{up.name if up else 'people_data.xlsx (on record)'}**")

    as_of = pd.Timestamp(st.date_input("As of", value=default_as_of(d).date(), format="MM/DD/YYYY",
                                       help="All numbers are calculated as of the start of this day. "
                                            "Defaults to the 1st of the month after the latest data."))
    ld = p.leaders(d, as_of)
    options = [None] + ld["employee_id"].tolist()
    labels = {None: "Whole company"} | dict(zip(ld["employee_id"], ld["label"]))
    leader = st.selectbox("Leader's org", options, format_func=lambda i: labels[i],
                          help="Type a name to search. Includes everyone who rolls up to this leader, at every level.")
    include_leader = st.toggle("Count the leader in their own org", value=True)
    wt_choice = st.radio("Worker type", ["FTEs only", "All workers (incl. contractors & interns)"],
                         help="HR reporting standard is FTEs only. Contractors and interns have no TCC.")
    st.divider()
    st.caption("Definitions are in the **Data health & definitions** tab. "
               "Questions? Contact People Intelligence.")

if as_of - pd.DateOffset(years=2) < p.data_start(d):
    st.sidebar.warning(f"Exit records start {p.data_start(d):%b %-d, %Y}. Attrition windows before that date are "
                       "shortened to the available data.")
worker_types = ["FTE"] if wt_choice == "FTEs only" else ["FTE", "Contractor", "Intern"]
org = p.org_ids(d, leader, include_leader)
_ln = labels[leader].split(" — ")[0] if leader is not None else ""
org_name = "the whole company" if leader is None else f"{_ln}{chr(39) if _ln.endswith('s') else chr(39) + 's'} org"
ttm_end = as_of - pd.Timedelta(days=1)
ttm = [("Prior 12 mo", as_of - pd.DateOffset(years=2), as_of - pd.DateOffset(years=1) - pd.Timedelta(days=1)),
       ("Last 12 mo", as_of - pd.DateOffset(years=1), ttm_end)]
quarters = p.quarters_back(as_of, 8, p.data_start(d))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def money(x, short=True):
    if pd.isna(x):
        return "—"
    if short and abs(x) >= 1e6:
        return f"${x/1e6:,.2f}M"
    if short and abs(x) >= 1e3:
        return f"${x/1e3:,.0f}K"
    return f"${x:,.0f}"


def pct(x, nd=1):
    return "—" if pd.isna(x) else f"{x*100:.{nd}f}%"


def style(fig, height=340, ytitle=None, yfmt=None):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="white",
                      paper_bgcolor="white", font=dict(color=INK, size=13), hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      bargap=0.35)
    fig.update_xaxes(showgrid=False, linecolor=LIGHTGRAY, tickfont=dict(color=INK2))
    fig.update_yaxes(gridcolor="#eeeeec", zeroline=False, tickfont=dict(color=INK2), title=ytitle,
                     tickformat=yfmt)
    return fig


def download(df: pd.DataFrame, name: str, label="Download table (CSV)"):
    st.download_button(label, df.to_csv(index=False).encode(), file_name=name, mime="text/csv",
                       key=f"dl_{name}")


def answer(q, text):
    st.markdown(f'<div class="answer"><b class="q">{q}</b>{text}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Core computations for the current selection
# --------------------------------------------------------------------------- #
for _c in ("director", "vp"):
    d.stints[_c] = d.stints[_c].replace("—", "(leader, no " + _c.replace("vp", "VP").replace("director", "Director") + " above)")
ros = p.roster(d, as_of, org, worker_types)
ros_fte = ros[ros["is_fte"]]
year_start = pd.Timestamp(as_of.year - 1, 12, 31) if as_of.month > 1 or as_of.day > 1 else pd.Timestamp(as_of.year - 2, 12, 31)
hc_dates = sorted(set([year_start] + p.month_ends(year_start + pd.Timedelta(days=1), ttm_end) + [as_of]))
hc = p.headcount_series(d, hc_dates, org, worker_types)
hc_start, hc_now = int(hc.iloc[0]["headcount"]), int(hc.iloc[-1]["headcount"])
att_q = p.attrition(d, quarters, org, ["FTE"])
att_ttm = p.attrition(d, ttm, org, ["FTE"])
fy_ttm = p.attrition(d, ttm, org, ["FTE"], tenure="lt1")
ten_ttm = p.attrition(d, ttm, org, ["FTE"], tenure="ge1")

# --------------------------------------------------------------------------- #
# Header + KPI row
# --------------------------------------------------------------------------- #
st.markdown(f"## {org_name[0].upper() + org_name[1:]}")
st.caption(f"As of **{as_of:%B %-d, %Y}** · {'FTEs only' if worker_types == ['FTE'] else 'All workers'} · "
           f"Attrition and TCC are always FTE-based")

k = st.columns(5)
k[0].metric("Headcount", f"{hc_now:,}", f"{hc_now - hc_start:+,} since {year_start:%b %-d}", delta_color="off",
            help="People employed at the start of the as-of day.")
k[1].metric("Annualized TCC (FTEs)", money(ros_fte["tcc_usd"].sum()),
            help="Annual base (hourly × 2,080) + annual target bonus, in USD at the entity FX rate.")
v_now, v_prev = att_ttm.iloc[1]["annualized_rate"], att_ttm.iloc[0]["annualized_rate"]
k[2].metric("Voluntary attrition, last 12 mo", pct(v_now),
            None if pd.isna(v_prev) else f"{(v_now - v_prev)*100:+.1f} pts vs prior 12 mo", delta_color="inverse")
f_now, f_prev = fy_ttm.iloc[1]["annualized_rate"], fy_ttm.iloc[0]["annualized_rate"]
k[3].metric("First-year voluntary attrition", pct(f_now),
            None if pd.isna(f_prev) else f"{(f_now - f_prev)*100:+.1f} pts vs prior 12 mo", delta_color="inverse",
            help="Voluntary exits within 12 months of hire ÷ average headcount with <12 months tenure.")
k[4].metric("Voluntary exits, last 12 mo", f"{int(att_ttm.iloc[1]['exits'])}",
            f"{int(att_ttm.iloc[1]['exits'] - att_ttm.iloc[0]['exits']):+d} vs prior 12 mo", delta_color="inverse")

tabs = st.tabs(["Quick answers", "Headcount", "Compensation (TCC)", "Attrition", "First-year attrition",
                "Data health & definitions"])

# --------------------------------------------------------------------------- #
# Tab 0: Quick answers — the recurring HRBP questions, in sentences
# --------------------------------------------------------------------------- #
with tabs[0]:
    st.markdown("Plain-English answers to the questions HRBPs ask most, for the org and date you picked in "
                "the sidebar. Copy and paste them as they are.")
    hdr_fte = len(p.active_on(d, as_of, org, ["FTE"]))
    answer("Current FTE headcount",
           f"<b>{hdr_fte:,} FTEs</b> in {org_name} as of {as_of:%b %-d, %Y}"
           + ("" if leader is None else f" ({'including' if include_leader else 'excluding'} the leader)")
           + f". Including contractors and interns: {len(p.active_on(d, as_of, org)):,}.")
    answer("Annualized TCC, FTEs only",
           f"<b>{money(ros_fte['tcc_usd'].sum(), short=False)}</b> = base {money(ros_fte['base_usd'].sum(), False)} "
           f"+ target bonus {money(ros_fte['bonus_usd'].sum(), False)}, across {len(ros_fte):,} FTEs, in USD.")
    hc_fte = p.headcount_series(d, hc_dates, org, ["FTE"])
    mv = p.movements(d, year_start + pd.Timedelta(days=1), ttm_end, org, ["FTE"])
    a0, a1 = int(hc_fte.iloc[0]["headcount"]), int(hc_fte.iloc[-1]["headcount"])
    last3 = mv.tail(3)
    net3 = int((last3["hires"] - last3["voluntary_exits"] - last3["involuntary_exits"]).sum())
    answer("Is headcount growing this year?",
           f"FTE headcount went from <b>{a0:,}</b> on {year_start:%b %-d} to <b>{a1:,}</b> "
           f"({a1-a0:+,}, {((a1/a0-1) if a0 else 0):+.1%}). Hires: {int(mv['hires'].sum())}. "
           f"Exits: {int(mv['voluntary_exits'].sum() + mv['involuntary_exits'].sum())}. "
           f"Net change over the last 3 months: <b>{net3:+d}</b>"
           + (" (growth has stalled)." if net3 <= 3 and a1 > a0 else "."))
    full = att_q[~att_q["period"].str.contains("partial")]
    last_q = att_q.iloc[-1]
    answer("Is voluntary attrition getting better or worse?",
           f"Last 12 months: <b>{pct(v_now)}</b> annualized vs {pct(v_prev)} in the prior 12 months "
           f"(<b>{'worse' if v_now > v_prev else 'better' if v_now < v_prev else 'flat'}</b>). "
           f"Most recent quarter, {last_q['period']}: {pct(last_q['annualized_rate'])} annualized "
           f"({int(last_q['exits'])} exits). See the Attrition tab for every quarter.")
    t_now = ten_ttm.iloc[1]["annualized_rate"]
    answer("Are first-year employees leaving at a higher rate?",
           f"First-year voluntary attrition is <b>{pct(f_now)}</b> (last 12 months) vs <b>{pct(t_now)}</b> for "
           f"people with 12+ months, i.e. <b>{(f_now/t_now if t_now else float('nan')):.1f}×</b> higher. "
           f"It was {pct(f_prev)} in the prior 12 months, so it is "
           f"<b>{'getting worse' if f_now > f_prev else 'improving'}</b>. Note that small orgs have small numbers. "
           f"Check the exit counts in the First-year tab before drawing conclusions.")

# --------------------------------------------------------------------------- #
# Tab 1: Headcount
# --------------------------------------------------------------------------- #
with tabs[1]:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("##### Month-end headcount")
        span = st.radio("Range", ["This year", "Last 24 months"], horizontal=True, label_visibility="collapsed")
        if span == "This year":
            series = hc
        else:
            dates24 = sorted(set(p.month_ends(as_of - pd.DateOffset(months=24), ttm_end) + [as_of]))
            series = p.headcount_series(d, dates24, org, worker_types)
        fig = go.Figure(go.Scatter(x=series["date"], y=series["headcount"], mode="lines+markers",
                                   line=dict(color=BLUE, width=2), marker=dict(size=8),
                                   name="Headcount", hovertemplate="%{x|%b %d, %Y}: %{y:,}<extra></extra>"))
        lo, hi = series["headcount"].min(), series["headcount"].max()
        pad = max(5, (hi - lo) * 0.25)
        fig.update_yaxes(range=[lo - pad, hi + pad])
        st.plotly_chart(style(fig, ytitle="Headcount"), width="stretch")
        if series["date"].min() < p.data_start(d):
            st.caption("⚠️ Before exits were first recorded "
                       f"({p.data_start(d):%b %-d, %Y}), headcount is understated: earlier leavers aren't in the file.")
    with c2:
        st.markdown("##### Hires and exits by month (FTE)")
        mvp = p.movements(d, year_start + pd.Timedelta(days=1), ttm_end, org, ["FTE"])
        x = mvp.index.to_timestamp()
        fig = go.Figure()
        fig.add_bar(x=x, y=mvp["hires"], name="Hires", marker_color=BLUE)
        fig.add_bar(x=x, y=-(mvp["voluntary_exits"]), name="Voluntary exits", marker_color=ORANGE)
        fig.add_bar(x=x, y=-(mvp["involuntary_exits"]), name="Involuntary exits", marker_color=GRAY)
        fig.update_layout(barmode="relative")
        fig.update_traces(hovertemplate="%{fullData.name}: %{y:,}<extra></extra>")
        fig.update_xaxes(tickformat="%b")
        st.plotly_chart(style(fig, ytitle="People (exits shown below zero)"), width="stretch")
    st.markdown("##### Where the headcount sits")
    dim = st.radio("Group by", ["director", "dept_name", "job_level", "location", "entity_name", "worker_type"],
                   horizontal=True,
                   format_func=lambda x: {"director": "Director", "dept_name": "Department", "job_level": "Level",
                                          "location": "Location", "entity_name": "Legal entity",
                                          "worker_type": "Worker type"}[x])
    tbl = ros.groupby(dim).agg(headcount=("stint_id", "size"),
                               first_year=("tenure_days", lambda s: int((s < 365).sum()))).reset_index()
    tbl = tbl.sort_values("headcount", ascending=False)
    tbl["% of org"] = (tbl["headcount"] / tbl["headcount"].sum()).map(pct)
    tbl = tbl.rename(columns={dim: "Group", "headcount": "Headcount", "first_year": "In first year"})
    st.dataframe(tbl, hide_index=True, width="stretch")
    cols = ["employee_id", "full_name", "job_level", "worker_type", "dept_name", "director", "vp", "location",
            "entity_name", "hire_date", "tenure_days"]
    download(ros[cols].sort_values("full_name"), f"roster_{as_of:%Y%m%d}.csv", "Download roster (CSV)")

# --------------------------------------------------------------------------- #
# Tab 2: Compensation
# --------------------------------------------------------------------------- #
with tabs[2]:
    f = ros_fte
    c = st.columns(4)
    c[0].metric("Annualized TCC", money(f["tcc_usd"].sum()))
    c[1].metric("Base pay", money(f["base_usd"].sum()))
    c[2].metric("Target bonus", money(f["bonus_usd"].sum()))
    c[3].metric("Median TCC per FTE", money(f["tcc_usd"].median()))
    missing = int(f["base_usd"].isna().sum())
    if missing:
        st.warning(f"{missing} FTE(s) have no base pay on file. They are counted in headcount but add $0 to TCC.")
    dim = st.radio("Break down by", ["director", "dept_name", "job_level", "entity_name"], horizontal=True,
                   format_func=lambda x: {"director": "Director", "dept_name": "Department", "job_level": "Level",
                                          "entity_name": "Legal entity (currency)"}[x], key="tcc_dim")
    g = f.groupby(dim).agg(FTEs=("stint_id", "size"), base=("base_usd", "sum"), bonus=("bonus_usd", "sum"),
                           tcc=("tcc_usd", "sum"), median_tcc=("tcc_usd", "median")).reset_index()
    g = g.sort_values("tcc", ascending=True)
    fig = go.Figure()
    fig.add_bar(y=g[dim], x=g["base"], name="Base", orientation="h", marker_color=BLUE,
                hovertemplate="%{y}<br>Base: $%{x:,.0f}<extra></extra>")
    fig.add_bar(y=g[dim], x=g["bonus"], name="Target bonus", orientation="h", marker_color=ORANGE,
                hovertemplate="%{y}<br>Target bonus: $%{x:,.0f}<extra></extra>")
    fig.update_layout(barmode="stack", hovermode="closest", legend_traceorder="normal")
    st.plotly_chart(style(fig, height=max(260, 34 * len(g) + 80), yfmt=None).update_xaxes(tickprefix="$"),
                    width="stretch")
    show = g.sort_values("tcc", ascending=False).rename(columns={dim: "Group"})
    for col in ["base", "bonus", "tcc", "median_tcc"]:
        show[col] = show[col].map(lambda v: money(v, False))
    show.columns = ["Group", "FTEs", "Base", "Target bonus", "TCC", "Median TCC"]
    st.dataframe(show, hide_index=True, width="stretch")
    st.caption("TCC = latest annual base effective on or before the as-of date (hourly × 2,080) + latest annual "
               "target bonus, converted to USD at the FX rate in the legal_entities sheet. Pay changes dated after "
               "the as-of date are excluded until they take effect.")

# --------------------------------------------------------------------------- #
# Tab 3: Attrition
# --------------------------------------------------------------------------- #
with tabs[3]:
    kind = st.radio("Exit type", ["Voluntary", "Involuntary", "All"], horizontal=True)
    tt = None if kind == "All" else kind
    aq = p.attrition(d, quarters, org, ["FTE"], term_type=tt)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"##### {kind} attrition by quarter (annualized, FTE)")
        colors = ["#86b6ef" if "partial" in s else BLUE for s in aq["period"]]
        fig = go.Figure(go.Bar(x=aq["period"].str.replace(" (partial)", "*", regex=False), y=aq["annualized_rate"],
                               marker_color=colors, text=aq["annualized_rate"].map(lambda v: pct(v)),
                               textposition="outside", textfont=dict(color=INK2),
                               customdata=aq[["exits", "avg_headcount"]],
                               hovertemplate="%{x}<br>Annualized: %{y:.1%}<br>Exits: %{customdata[0]}"
                                             "<br>Avg headcount: %{customdata[1]:,.0f}<extra></extra>"))
        fig.update_layout(hovermode="closest")
        st.plotly_chart(style(fig, ytitle="Annualized rate", yfmt=".0%"), width="stretch")
        st.caption("\\* Partial quarter (lighter bar). The rate is annualized so partial quarters are comparable, "
                   "but they rest on fewer exits.")
    with c2:
        st.markdown("##### Exit reasons, last 12 months vs prior")
        s = p._filter(d.stints, org, ["FTE"])
        rows = []
        for lab, a, b in ttm:
            ex = s[(s["termination_date"] >= a) & (s["termination_date"] <= b)]
            if tt:
                ex = ex[ex["termination_type"] == tt]
            rows.append(ex["reason"].value_counts().rename(lab))
        r = pd.concat(rows, axis=1).fillna(0).astype(int).sort_values("Last 12 mo")
        fig = go.Figure()
        fig.add_bar(y=r.index, x=r["Prior 12 mo"], name="Prior 12 mo", orientation="h", marker_color=LIGHTGRAY)
        fig.add_bar(y=r.index, x=r["Last 12 mo"], name="Last 12 mo", orientation="h", marker_color=BLUE)
        fig.update_layout(barmode="group", hovermode="y unified")
        st.plotly_chart(style(fig, height=340), width="stretch")
    tbl = aq.assign(**{"Period": aq["period"], "Exits": aq["exits"],
                       "Avg headcount": aq["avg_headcount"].round(1),
                       "Quarter rate": aq["period_rate"].map(pct),
                       "Annualized rate": aq["annualized_rate"].map(pct),
                       "From": aq["start"].dt.strftime("%b %d, %Y"), "To": aq["end"].dt.strftime("%b %d, %Y")})
    tbl = tbl[["Period", "From", "To", "Exits", "Avg headcount", "Quarter rate", "Annualized rate"]]
    st.dataframe(tbl, hide_index=True, width="stretch")
    download(tbl, f"attrition_by_quarter_{as_of:%Y%m%d}.csv")
    st.caption(f"Exit records start {p.data_start(d):%b %-d, %Y}, so earlier quarters can't be calculated. "
               "Rate = exits ÷ average daily headcount in the period. Annualized = × 365 ÷ days in period.")

# --------------------------------------------------------------------------- #
# Tab 4: First-year attrition
# --------------------------------------------------------------------------- #
with tabs[4]:
    st.markdown("Voluntary exits of people in their **first 12 months**, compared with everyone else. "
                "Each group's rate uses its own headcount: first-year exits ÷ average first-year headcount.")
    a = p.attrition(d, quarters, org, ["FTE"], tenure="lt1")
    b = p.attrition(d, quarters, org, ["FTE"], tenure="ge1")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("##### Voluntary attrition: first year vs 12+ months (annualized)")
        xlab = a["period"].str.replace(" (partial)", "*", regex=False)
        fig = go.Figure()
        fig.add_scatter(x=xlab, y=a["annualized_rate"], name="First year (<12 mo)", mode="lines+markers",
                        line=dict(color=ORANGE, width=2), marker=dict(size=8), customdata=a[["exits"]],
                        hovertemplate="First year: %{y:.1%} (%{customdata[0]} exits)<extra></extra>")
        fig.add_scatter(x=xlab, y=b["annualized_rate"], name="12+ months", mode="lines+markers",
                        line=dict(color=BLUE, width=2), marker=dict(size=8), customdata=b[["exits"]],
                        hovertemplate="12+ months: %{y:.1%} (%{customdata[0]} exits)<extra></extra>")
        st.plotly_chart(style(fig, ytitle="Annualized rate", yfmt=".0%"), width="stretch")
        st.caption("\\* Partial quarter.")
    with c2:
        st.markdown("##### Last 12 months")
        m1, m2 = st.columns(2)
        m1.metric("First year", pct(f_now), f"{(f_now - f_prev)*100:+.1f} pts" if pd.notna(f_prev) else None,
                  delta_color="inverse")
        m2.metric("12+ months", pct(t_now),
                  f"{(t_now - ten_ttm.iloc[0]['annualized_rate'])*100:+.1f} pts", delta_color="inverse")
        st.markdown(f"<span class='note'>First-year exits: <b>{int(fy_ttm.iloc[1]['exits'])}</b> out of an average of "
                    f"<b>{fy_ttm.iloc[1]['avg_headcount']:.0f}</b> first-year employees. 12+ months: "
                    f"<b>{int(ten_ttm.iloc[1]['exits'])}</b> out of <b>{ten_ttm.iloc[1]['avg_headcount']:.0f}</b>.</span>",
                    unsafe_allow_html=True)
    st.markdown("##### Hire cohorts: share who left within 12 months / 90 days")
    coh = p.hire_cohort_retention(d, as_of, org, ["FTE"])
    coh = coh[coh["hires"] > 0]
    fig = go.Figure()
    fig.add_bar(x=coh.index, y=coh["pct_vol_1yr"], name="Resigned within 12 months",
                marker_color=[ORANGE if fo else "#f5b89e" for fo in coh["full_year_observed"]],
                customdata=coh[["hires", "vol_within_1yr"]],
                hovertemplate="%{x} hires: %{customdata[0]}<br>Resigned within 12 mo: %{customdata[1]} "
                              "(%{y:.0%})<extra></extra>")
    fig.add_scatter(x=coh.index, y=coh["pct_left_90d"], name="Left within 90 days (any reason)",
                    mode="lines+markers", line=dict(color=INK2, width=2), marker=dict(size=8),
                    hovertemplate="Left within 90 days: %{y:.0%}<extra></extra>")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style(fig, ytitle="% of hires", yfmt=".0%"), width="stretch")
    st.caption("Lighter bars are cohorts that haven't completed 12 months yet, so their figure will keep rising. "
               "Cohorts hired before exits were tracked are excluded.")
    st.markdown("##### Where first-year exits are concentrated (last 12 months)")
    dim = st.radio("Group by", ["vp", "director", "dept_name", "job_level", "location"], horizontal=True,
                   index=0 if leader is None else 1,
                   format_func=lambda x: {"vp": "VP", "director": "Director", "dept_name": "Department",
                                          "job_level": "Level", "location": "Location"}[x], key="fy_dim")
    ab = p.attrition_by(d, dim, ttm[1][1], ttm[1][2], org, ["FTE"], tenure="lt1")
    ab_prev = p.attrition_by(d, dim, ttm[0][1], ttm[0][2], org, ["FTE"], tenure="lt1")
    ten_b = p.attrition_by(d, dim, ttm[1][1], ttm[1][2], org, ["FTE"], tenure="ge1")
    tb = ab.merge(ab_prev[[dim, "annualized_rate"]], on=dim, how="left", suffixes=("", "_prev")) \
           .merge(ten_b[[dim, "annualized_rate"]].rename(columns={"annualized_rate": "ten"}), on=dim, how="left")
    tb = tb[tb["avg_headcount"] > 0]
    tb["flag"] = (tb["avg_headcount"] < 5).map({True: "small group", False: ""})
    out = pd.DataFrame({"Group": tb[dim], "First-year exits": tb["exits"],
                        "Avg first-year headcount": tb["avg_headcount"].round(1),
                        "First-year rate": tb["annualized_rate"].map(pct),
                        "Prior 12 mo": tb["annualized_rate_prev"].map(pct),
                        "12+ mo rate": tb["ten"].map(pct), "Note": tb["flag"]})
    st.dataframe(out, hide_index=True, width="stretch")
    download(out, f"first_year_by_{dim}_{as_of:%Y%m%d}.csv")
    st.caption("Groups averaging fewer than 5 first-year employees are marked 'small group'. A single exit swings "
               "their rate a lot. Attrition by front-line manager isn't shown: in this file, leavers are re-pointed "
               "to their Director, so the Director is the lowest reliable level.")

# --------------------------------------------------------------------------- #
# Tab 5: Data health & definitions
# --------------------------------------------------------------------------- #
with tabs[5]:
    iss = p.add_asof_issues(d, as_of)
    hi = int((iss["severity"] == "High").sum())
    st.markdown(f"Every upload is checked automatically. **{len(iss)} checks flagged, {hi} high-severity.** "
                "Each one is already handled in the numbers above, as described in the right-hand column. "
                "Send the IDs to HRIS so the source data gets fixed.")
    sev_icon = {"High": "🔴 High", "Medium": "🟠 Medium", "Low": "⚪ Low", "Info": "🔵 Info"}
    view = iss.assign(severity=iss["severity"].map(sev_icon)).rename(columns={
        "check": "Check", "severity": "Severity", "records": "Records", "detail": "Detail",
        "handling": "How it's handled", "example_ids": "Example IDs"})
    st.dataframe(view, hide_index=True, width="stretch",
                 column_config={"How it's handled": st.column_config.TextColumn(width="large"),
                                "Detail": st.column_config.TextColumn(width="medium")})
    download(iss, f"data_issues_{as_of:%Y%m%d}.csv", "Download issue log (CSV)")

    st.markdown("##### Reconciliation with the team's monthly_summary sheet")
    rec = p.reconcile_monthly_summary(d)
    bad = rec[(rec[["diff_headcount", "diff_first_year", "diff_voluntary", "diff_involuntary"]] != 0).any(axis=1)]
    if bad.empty:
        st.success("The hand-kept monthly_summary matches the rebuilt numbers in every month.")
    else:
        st.info(f"{len(rec) - len(bad)} of {len(rec)} months match exactly. These months differ "
                "(sheet value minus rebuilt value):")
        st.dataframe(bad[["month_end", "fte_headcount", "calc_fte_headcount", "voluntary_terms", "calc_voluntary",
                          "involuntary_terms", "calc_involuntary"]].assign(
            month_end=bad["month_end"].dt.strftime("%b %Y")).rename(columns={
                "month_end": "Month", "fte_headcount": "Sheet: FTE headcount", "calc_fte_headcount": "Rebuilt: FTE headcount",
                "voluntary_terms": "Sheet: voluntary exits", "calc_voluntary": "Rebuilt: voluntary exits",
                "involuntary_terms": "Sheet: involuntary exits", "calc_involuntary": "Rebuilt: involuntary exits"}),
            hide_index=True, width="stretch")
        notes = []
        for r_ in bad.itertuples():
            m0, m1 = r_.month_end.replace(day=1), r_.month_end
            nonfte = d.stints[(~d.stints["is_fte"]) & d.stints["termination_date"].between(m0, m1)]
            if r_.diff_voluntary and len(nonfte) == r_.diff_voluntary:
                notes.append(f"{r_.month_end:%b %Y}: the sheet's extra {int(r_.diff_voluntary)} voluntary exit(s) "
                             f"equal that month's {len(nonfte)} non-FTE exits ({', '.join(nonfte['reason'].unique())}), "
                             "so they were probably counted by mistake.")
        if notes:
            st.caption(" ".join(notes))

    st.markdown("##### Definitions")
    st.markdown(f"""
- **Headcount** counts people whose hire date is on or before the as-of date and who have no exit on or before it. It's FTEs unless you choose otherwise.
- **Org** means the leader plus everyone below them in the reporting line, at every level. It uses the current reporting lines. Leavers count toward the leader they last rolled up to.
- **TCC (total cash compensation)** is annual base pay plus annual target bonus. Hourly pay is multiplied by {p.HOURS_PER_YEAR:,} hours. Everything is converted to USD using the legal_entities FX rates. It includes FTEs only.
- **Voluntary / involuntary** comes from termination_type in the exit log. FTEs only, so intern and contractor endings are excluded.
- **Attrition rate** = exits ÷ average daily headcount over the period. **Annualized** = rate × 365 ÷ days in the period, so quarters and partial quarters are comparable.
- **First year** means fewer than {p.FIRST_YEAR_DAYS} days from hire. The first-year rate uses first-year exits ÷ average first-year headcount.
- **Rehires** are treated as a new employment period. Tenure restarts at the rehire date.
- **Refreshing next month:** upload the new export in the sidebar. The as-of date moves automatically to the 1st of the following month, and every number and data check recalculates.
""")
