const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  HeadingLevel, AlignmentType, LevelFormat, ImageRun, BorderStyle, Footer, PageNumber, PageBreak,
} = require("docx");

const BLUE = "2A78D6", INK = "1F1F1E", INK2 = "52514E", RULE = "D9D8D4", TINT = "EEF4FC";
const FONT = "Calibri";
const W = 9360; // content width (DXA) on US Letter with 1" margins

const r = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 21, bold: o.bold, italics: o.italics, color: o.color || INK });
// parse **bold** inline
const runs = (s, o = {}) => s.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(t =>
  t.startsWith("**") ? r(t.slice(2, -2), { ...o, bold: true }) : r(t, o));
const P = (s, o = {}) => new Paragraph({ children: runs(s, o), spacing: { after: o.after ?? 120, line: 276 }, alignment: o.align });
const H1 = s => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [r(s, { size: 30, bold: true, color: INK })],
  spacing: { before: 320, after: 140 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE, space: 4 } } });
const H2 = s => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [r(s, { size: 24, bold: true, color: BLUE })],
  spacing: { before: 220, after: 90 } });
const B = (s, lvl = 0) => new Paragraph({ numbering: { reference: "bul", level: lvl }, children: runs(s), spacing: { after: 60, line: 264 } });
const N = (s, ref = "num") => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(s), spacing: { after: 80, line: 264 } });

function table(header, rows, widths, o = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (txt, i, head, shade) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { type: ShadingType.CLEAR, fill: "F2F2F0", color: "auto" } : shade ? { type: ShadingType.CLEAR, fill: TINT, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ alignment: (o.right || []).includes(i) ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: runs(String(txt), { size: o.size || 18, bold: head, color: head ? INK2 : INK }) })],
  });
  const border = { style: BorderStyle.SINGLE, size: 4, color: RULE };
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    borders: { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border },
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map((row, ri) => new TableRow({ children: row.map((c, i) => cell(c, i, false, (o.shadeRows || []).includes(ri))) }))],
  });
}
const img = (file, w, h) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 80 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(__dirname, file)), transformation: { width: w, height: h } })] });
const N2 = (s) => N(s, "num2");
const callout = (s) => new Table({
  width: { size: W, type: WidthType.DXA }, columnWidths: [W],
  borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
    left: { style: BorderStyle.SINGLE, size: 24, color: BLUE }, insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE } },
  rows: [new TableRow({ children: [new TableCell({ width: { size: W, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: TINT, color: "auto" }, margins: { top: 100, bottom: 100, left: 180, right: 160 },
    children: (Array.isArray(s) ? s : [s]).map(t => new Paragraph({ children: runs(t), spacing: { after: 60, line: 264 } })) })] })],
});
const sp = (n = 120) => new Paragraph({ spacing: { after: n }, children: [] });

const body = [
  new Paragraph({ children: [r("People Intelligence Take-Home Case", { size: 40, bold: true })], spacing: { after: 60 } }),
  new Paragraph({ children: [r("Write-up · Mike Spencer · Associate, People Intelligence · Fanatics Collectibles", { size: 22, color: INK2 })], spacing: { after: 40 } }),
  new Paragraph({ children: [r("All answers are as of September 1, 2026 (start of day), from people_data.xlsx.", { size: 20, color: INK2, italics: true })], spacing: { after: 200 } }),

  callout([
    "**What's attached:** (1) **The HRBP dashboard**, a hosted Streamlit app: [DASHBOARD LINK]. (2) **people-intel.zip**, the working files: pipeline.py (all logic), app.py (dashboard), analysis/answers.py (reproduces every number below), analysis/verify_independent.py (independent cross-check) and analysis/output (answers workbook). (3) This write-up.",
    "**Next month:** an HRBP opens the link, uploads the new export (or we replace the file on record), and picks their leader. Every number, chart and data-quality check recalculates. They never touch code or formulas.",
  ]),
  sp(60),

  H1("Answers at a glance"),
  table(["#", "Question", "Answer (as of Sep 1, 2026)"], [
    ["1", "FTE headcount, Morgan Reyes' org", "**418 FTEs** (Morgan + everyone who rolls up to him). 417 excluding Morgan."],
    ["2", "Annualized TCC, Dana Whitfield's org, FTEs", "**$45,439,575** (base $44.05M + target bonus $1.39M; 552 FTEs)."],
    ["3", "Headcount trend this year", "**Yes, growing, but stalling.** 1,935 on Dec 31 to 1,991 (+56, +2.9%). Net growth Jun–Aug was just +7, and August was negative."],
    ["4", "Voluntary attrition by quarter", "**Worse.** 5.5% annualized (Q4 2024) to 7–8% (2025), then 8.5%, 10.2% and 12.1% across 2026. Trailing 12 months: 7.0% to 9.2%."],
    ["5", "First-year attrition", "**Yes, ~4x higher and rising fast.** First-year voluntary attrition is 27.5% vs 6.3% for 12+ months, and roughly doubled from 13.1% a year ago. It's tenure, not age."],
    ["6", "Anything else", "Commercial (Morgan's org) is shrinking and is the attrition hot spot. Several data traps would have produced wrong answers. Details below."],
  ], [500, 3100, 5760]),

  H1("1 · FTE headcount for Morgan Reyes' org"),
  callout("**418 FTEs** (417 if Morgan himself is excluded). Including 13 contractors and 4 interns, the total is 435."),
  sp(40),
  P("**Method.** Morgan's org is everyone below him in manager_hierarchy, at every level, plus Morgan. A person counts if they were hired on or before Sep 1, 2026 and have no exit on or before that date. Morgan has four Directors under him: Genesis Clark (Sales, 140), Elijah MacDonald (Customer Service, 103), Yusuf Ruiz (Marketing, 88) and Pierre OBrien (E-Commerce, 86)."),
  P("**Why it isn't a simple filter.** Shortcut approaches give anything from 396 to 422. Filtering on employment_status = \"Active\" misses the \"ACTIVE\" rows (415). Skipping the dedupe and the status fix double-counts and includes a leaver (422). Filtering on dept codes D10–D13 misses lower-case codes like \"d10\", and Morgan's own record is one of them (396). One person in his org is marked Active but resigned on Jul 15, 2026 (ID 8086). I count them as gone."),

  H1("2 · Annualized TCC for Dana Whitfield's org (FTEs)"),
  callout("**$45,439,575** across 552 FTEs: base $44,052,620 + target bonus $1,386,955, in USD."),
  sp(40),
  P("**Method.** For each FTE active on Sep 1, I took the latest Base and the latest Target Bonus effective on or before Sep 1. Hourly rates are annualized at 2,080 hours, and 213 of Dana's FTEs are hourly (Manufacturing). Each record is converted to USD at the legal_entities FX rate for its currency. Dana's org spans four entities: US $29.67M (378), UK $9.17M (91, GBP × 1.28), Netherlands $3.36M (36, EUR × 1.09) and Canada $3.24M (47, CAD × 0.74)."),
  P("**What to watch.** A naive sum gives **$32.8M**: it leaves hourly rates un-annualized, ignores FX, and picks up 40 pay changes dated Oct 1, 2026 that aren't effective yet. Ignoring FX alone gives $44.29M. The Oct 1 changes add about $42K to Dana's org once effective, and the dashboard picks them up automatically."),

  H1("3 · Is headcount growing this year?"),
  callout("**Yes, but growth has stalled.** FTE headcount rose from 1,935 (Dec 31, 2025) to 1,991 (Sep 1, 2026): +56, or +2.9%. Most of that came in H1. Net adds for Jun–Aug totaled just +7, and August was the first net-negative month (−1)."),
  img("fig_headcount.png", 600, 220),
  P("**Why it's stalling.** Hiring has held steady at about 26 a month. Voluntary exits rose from about 14 a month in Jan–Apr to 20–22 a month in Jun–Aug, so exits now nearly match hires. For comparison, Jan–Aug 2025 added +74 (+4.1%). The total also hides a split: Morgan's Commercial org **shrank by 22 FTEs (−5%) this year** while the rest of the company grew by 78. Contractors (134 to 142) and summer interns (0 to 28) are excluded from these figures. With them, the total is 2,069 to 2,161."),

  H1("4 · Voluntary attrition by quarter"),
  callout("**Getting worse, and accelerating in 2026.** Annualized voluntary attrition has more than doubled since late 2024. On a trailing-12-month basis it rose from 7.0% to 9.2%."),
  img("fig_attrition.png", 600, 194),
  table(["Quarter", "Voluntary exits", "Avg FTE headcount", "Quarterly rate", "Annualized"], [
    ["2024 Q4", "25", "1,806", "1.4%", "5.5%"], ["2025 Q1", "35", "1,833", "1.9%", "7.7%"],
    ["2025 Q2", "36", "1,858", "1.9%", "7.8%"], ["2025 Q3", "36", "1,892", "1.9%", "7.5%"],
    ["2025 Q4", "34", "1,914", "1.8%", "7.0%"], ["2026 Q1", "41", "1,945", "2.1%", "8.5%"],
    ["2026 Q2", "50", "1,974", "2.5%", "10.2%"], ["2026 Q3 (Jul–Aug only)", "41", "1,990", "2.1% (2 mo)", "12.1%"],
  ], [2760, 1500, 1800, 1600, 1700], { right: [1, 2, 3, 4], shadeRows: [6, 7] }),
  sp(60),
  P("**Notes.** The rate is exits divided by average daily FTE headcount in the quarter. Annualized means × 365 ÷ days, so the partial quarter is comparable. The exit log only starts on Aug 15, 2024, so I show the eight quarters it fully covers. The Aug 15–Sep 30, 2024 stub was 5.2% annualized. Intern \"End of Internship\" exits are coded Voluntary in the source, and contractor contract-ends are Involuntary. Restricting to FTEs keeps both out. Involuntary attrition is flat at about 2%, so this is a resignation problem, not a separations one.", { size: 19 }),

  H1("5 · Are first-year employees leaving at a higher rate?"),
  callout(["**Yes, about 4x higher, and it's the main reason overall attrition is rising.** Over the last 12 months, first-year voluntary attrition was **27.5%** (74 resignations ÷ ~269 average first-year FTEs) vs **6.3%** for people with 12+ months. A year earlier the figures were 13.1% vs 5.5%. Since Q2 2026 the first-year rate has been running at **~40% annualized**, while the tenured rate is roughly flat.",
    "**It's about tenure, not age.** Measured by age, under-30s leave at the same rate as everyone else (9.4% vs 8.8–9.9%). Whatever is happening, it's happening in the first months on the job."]),
  img("fig_firstyear.png", 600, 227),
  H2("Where it's concentrated (last 12 months, first-year voluntary, annualized)"),
  table(["Cut", "First-year rate", "Prior 12 mo", "Exits / avg first-year HC"], [
    ["Commercial: Morgan Reyes' org", "54.9%", "16.8%", "30 / 55"],
    ["   Customer Service (Elijah MacDonald, Boise)", "68.7%", "10.2%", "10 / 15"],
    ["   Marketing (Yusuf Ruiz)", "56.1%", "24.6%", "7 / 12"],
    ["   Sales (Genesis Clark)", "49.2%", "19.4%", "8 / 16"],
    ["Technology: Grace Okafor's org", "30.5%", "14.6%", "9 / 30"],
    ["Manufacturing Ops: Dana Whitfield's org", "24.6%", "12.5%", "20 / 81"],
    ["Rest of company (excluding Commercial)", "20.6%", "12.1%", "44 / 214"],
  ], [4200, 1500, 1500, 2160], { right: [1, 2, 3], shadeRows: [0] }),
  sp(60),
  P("**Other signals.** Very early exits are the clearest warning sign: **13% of Q2 2026 hires left within 90 days**, against 0–5% for every earlier cohort, and that 13% is a floor because some June hires haven't reached 90 days yet. Among first-year leavers, \"Relocation\" (7 to 22) and \"Return to School\" (8 to 15) grew fastest. Starting pay is flat by level, and 2026 merit increases reached new hires at the same rate as tenured staff, so pay alone doesn't explain it. These are small groups (10–30 exits), so treat Director-level rates as directional."),
  H2("What I'd recommend"),
  N("**Triage Commercial now.** Have the HRBPs for Elijah MacDonald, Yusuf Ruiz and Genesis Clark run stay interviews with current first-year staff and call back the 30 first-year leavers from the last 12 months. Customer Service in Boise is the first place to look: 69% first-year attrition and 14% for tenured staff, the highest in the company."),
  N("**Fix the first 90 days.** The spike in very early exits points to a hiring-to-onboarding mismatch: role expectations, schedule or location, or manager readiness. The \"Relocation\" and \"Return to School\" reasons suggest some candidates weren't a fit for the location or a full-time commitment. Tighten realistic job previews and recruiter screening, and add structured 30/60/90-day check-ins with a named onboarding buddy."),
  N("**Make it a tracked KPI.** Report first-year and 90-day attrition by Director every month (it's already in the dashboard). Set a goal of getting back to the 2025 level (~13%) within two quarters, and check each new hire cohort against it."),
  N("**Fix the data so we can see the cause.** Today the hierarchy re-points leavers to their Director, so we can't tell whether a few front-line managers are driving this. That's often the biggest lever. Keep each leaver's actual manager (an effective-dated hierarchy), and add hire source and a structured exit survey."),

  H1("6 · Anything else worth flagging"),
  B("**Commercial is shrinking, and it's the attrition hot spot.** Morgan's org went from 440 to 418 FTEs this year. Its voluntary attrition is 15.5% vs 9.1% a year ago, and 29% annualized in Jul–Aug. August alone had 14 resignations against 5 hires. Company-level growth hides this, and it's worth raising with the CPO before Q4 planning."),
  B("**The hand-kept monthly_summary is mostly right, but it's hand-kept.** After I removed a duplicate identity (below), my rebuilt headcount and first-year counts match it exactly for all 24 months. But March 2026 shows 16 voluntary terms where there were 13. The extra 3 equal that month's contractor contract-ends. I'd retire the sheet in favor of the dashboard."),
  B("**The data model hides manager-level attrition.** Every active employee reports to a Manager, but all 529 leavers point to a Director. Either leavers are re-parented when they exit or the export takes a current snapshot. Either way, we can't measure the most actionable driver (see recommendation 4)."),
  B("**Pay compression.** 23 Senior Analysts (under 21 Managers) earn more base pay than their own Manager. It may be legitimate (specialist premium), but it's worth a look in the next comp cycle."),
  B("**Pay changes are coming.** 40 base-pay increases dated Oct 1, 2026 (+4% each, 24 of them Analysts) will move next month's TCC. They're excluded as of Sep 1, and the dashboard picks them up automatically."),
  B("**HRIS hygiene.** 63 hire dates fall on Jan 5, 2015, which looks like a system-migration default, so true tenure for long-serving staff is understated. 25 birth dates put the person under 16 at hire. 1 Active record has a resignation on file. I'd send the full issue log (in the dashboard) to HRIS."),

  H1("The tool: what an HRBP sees"),
  P("A hosted Streamlit app. There's nothing to install, and no code or formulas are exposed. In the sidebar the HRBP can **upload this month's file**, pick an **as-of date** (it defaults to the 1st of the month after the latest record), **search for any leader** (the CEO, VPs, Directors and all 298 Managers) and choose FTEs or all workers. Six tabs:"),
  B("**Quick answers:** questions 1–5 written out as sentences for the chosen org and date, ready to paste into a reply."),
  B("**Headcount:** month-end trend, hires vs exits, and a breakdown by director, department, level, location or entity. Includes a roster download."),
  B("**Compensation (TCC):** base and bonus split by director, department, level or entity, with the method stated on the page."),
  B("**Attrition:** voluntary, involuntary or all exits by quarter, annualized, with exit reasons compared year over year."),
  B("**First-year attrition:** first year vs 12+ months by quarter, hire-cohort 12-month and 90-day loss rates, and hot spots, with small groups flagged."),
  B("**Data health & definitions:** each upload is checked and every issue logged with how it was handled, plus an automatic reconciliation against the monthly_summary sheet."),
  P("**Design choices.** All logic lives in one tested module (pipeline.py), so the app, the answer script and future automation can't disagree. Rates are annualized so partial periods are comparable. Charts use a color-blind-safe palette, and exits always show raw counts alongside rates."),

  H1("Data issues found and how I handled them"),
  table(["Issue", "Scale", "Handling / assumption"], [
    ["employee_id is zero-padded text (\"02321\") in employees, comp and terms, but a number in manager_hierarchy", "All rows", "Cast to integer before every join. In Excel, a VLOOKUP of \"02321\" against 2321 fails silently."],
    ["Exact duplicate employee rows", "3", "Dropped the copies."],
    ["Same person under two IDs: \"Rob\" Calloway 3994 and \"Robert\" Calloway 11973 (same email, DOB, dept; 3994 has no pay)", "1", "Dropped 3994. This made my headcount match monthly_summary exactly in all 24 months."],
    ["Same ID with two hire dates (7532: left 2024, rehired Nov 2025)", "1", "Treated as two employment periods. Each exit is matched to the period it falls in, and tenure restarts at rehire."],
    ["Status \"Active\" but an exit is on file (8086, resigned Jul 15, 2026)", "1", "The termination log is the system of record. Counted as a voluntary exit; monthly_summary agrees."],
    ["Hire dates in 5 formats (ISO, M/D/YYYY, padded with spaces)", "1,083", "Parsed explicitly. Slash dates are M/D because day > 12 only ever appears second."],
    ["Lower-case dept codes (\"d10\"), status casing (\"ACTIVE\"), trailing spaces in location", "147 / 59 / 104", "Normalized. Otherwise people drop out of department and status filters."],
    ["Leavers point to a Director, not their actual manager", "529", "Org roll-ups are unaffected. Front-line manager attrition isn't reported; Director is the lowest reliable level."],
    ["Comp changes dated after the as-of date (Oct 1, 2026)", "40", "Ignored until effective, via as-of logic."],
    ["Hourly vs annual pay; 4 currencies", "770 hourly records", "Hourly × 2,080. Each record converted at the legal_entities FX rate for its currency."],
    ["Pay currency ≠ entity currency (USD pay in the EUR entity)", "7 interns", "Taken as recorded. No effect on FTE TCC. Flagged for Payroll."],
    ["\"End of Internship\" coded Voluntary; contractor exits coded Involuntary", "76 / 72", "FTE-only attrition excludes both. Flagged for reason-code cleanup."],
    ["Exit log starts Aug 15, 2024", "n/a", "Attrition before then can't be calculated. Windows are clipped to available data and labeled partial."],
    ["Hire-date spike on Jan 5, 2015; 25 implausible birth dates", "63 / 25", "Flagged. Doesn't affect any metric here."],
  ], [3700, 1000, 4660], { size: 17 }),
  sp(60),
  P("**Key definitions.** FTE = worker_type \"FTE\". Headcount on date D = hired on or before D with no exit on or before D (a same-day exit is not counted, which matches monthly_summary). Org = the leader plus all descendants in the current hierarchy. TCC = base + target bonus (not actual bonus paid; no equity or benefits). First year = under 365 days of tenure, compared against first-year headcount rather than total headcount.", { size: 19 }),

  H1("AI appendix"),
  P("I used Claude throughout, as a pair analyst. It profiled the workbook, drafted the pipeline, dashboard and charts, and helped draft this write-up. My job was to direct the analysis, make the judgment calls on definitions and data handling, and verify everything."),
  H2("How I verified the output"),
  B("**Independent re-implementation.** verify_independent.py rebuilds Q1–Q5 from the raw cells with plain Python (openpyxl, loops and sets) and doesn't import the pipeline. Every headline number matches."),
  B("**Reconciliation to an outside source.** The rebuilt monthly headcount, first-year headcount and exit counts were compared against the team's monthly_summary for all 24 months. Everything matches except one documented error in the sheet."),
  B("**Spot checks and edge cases.** I traced individual records (8086, 7532, 3994/11973, the 7 currency-mismatch rows), tested the app across every VP, several Directors, both worker-type modes and early as-of dates, and looked at every chart rendered."),
  H2("What I had to correct along the way"),
  B("**The first independent check disagreed:** Q1 came out as 0 and headcount was 1 too high. The cause was that IDs are text in some sheets and numbers in others, which pandas had silently coerced. That turned into a new data finding, and I hardened the pipeline to cast IDs explicitly."),
  B("**The first exit-matching logic dropped the rehire's current employment period** (7532). Caught through the monthly_summary reconciliation."),
  B("**A constant 1-person gap against monthly_summary** led me to the Rob/Robert Calloway duplicate identity, which a row-level dedupe can't catch."),
  B("**The first manager-level cut was wrong:** it made Directors look like they had very high attrition among their direct reports. I noticed Directors only manage Managers, found that leavers are re-pointed to Directors, and switched to Director/VP roll-ups."),
  B("**Manager names aren't unique** (159 repeated full names, e.g. two Yusuf Ruiz), so every leader is keyed by name plus ID."),
  B("**Attrition windows before Aug 15, 2024 were silently understated** for early as-of dates. They're now clipped to the available data and labeled."),
  B("**A first draft assumed the currency mismatch affected FTE TCC.** Checking showed all 7 records are interns, so there's no effect."),

  H1("If I had a week: running it monthly with no human touch"),
  N2("**Source:** replace the emailed workbook with a scheduled pull from the HRIS and payroll APIs (e.g. Workday RaaS) into the warehouse (Snowflake/BigQuery), landing a dated snapshot each month."),
  N2("**Model:** move pipeline.py's logic into dbt models: staging (typing, casing, dates), an employment-period table, an effective-dated reporting-line table, and monthly fact tables for headcount, TCC and attrition. Then every BI tool reads the same definitions."),
  N2("**Test:** turn each data-quality check into a dbt or Great Expectations test: unique IDs, no duplicate identities, status matches the exit log, valid FX, no hourly rate above $200. High-severity failures block publishing and alert the People Intelligence channel. Everything else goes to the issue log, with auto-created HRIS tickets."),
  N2("**Orchestrate:** run on the 1st of each month (Airflow, Dagster or a dbt Cloud job): extract, then test, then build, then refresh the dashboard, then post a one-paragraph summary of the month's key changes and new data issues to Slack and email."),
  N2("**Serve securely:** host the dashboard behind SSO with row-level security, so each HRBP only sees their own leaders' orgs. Hide pay below aggregate level unless the role allows it."),
  N2("**Monitor:** add a CI test suite (including the independent cross-check as a regression test), freshness alerts, and an anomaly check that flags any metric that moves more than about 3 standard deviations month over month for a human to review before it's published."),

  H1("Time spent"),
  P("**[FILL IN: total hours]**, roughly split as: reading the brief and profiling the data [__]; building and verifying the cleaning and metrics pipeline [__]; the analysis for Q4–Q6 [__]; building and testing the dashboard [__]; the write-up [__]."),
];

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 30, bold: true }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 24, bold: true }, paragraph: { outlineLevel: 1 } },
    ] },
  numbering: { config: [
    { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 240 } } } }] },
    { reference: "num2", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 300 } } } }] },
    { reference: "num", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1080, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [r("People Intelligence case · Mike Spencer · page ", { size: 16, color: INK2 }),
        new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: INK2 })] })] }) },
    children: body,
  }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(__dirname, "People_Intelligence_Case_Writeup_Mike_Spencer.docx"), b); console.log("ok"); });
