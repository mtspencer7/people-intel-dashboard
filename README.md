# People Intelligence: HRBP Self-Serve Dashboard

A click-around dashboard that answers the recurring HR Business Partner questions:
- headcount and annualized TCC for any leader's org,
- this year's headcount trend,
- voluntary attrition by quarter,
- first-year attrition,
- automated data-quality checks.

It works for any as-of date. Next month, an HRBP uploads the new `people_data.xlsx` (or an admin replaces the file in `data/`), and everything recalculates.

## What's in here

| File | What it is |
|---|---|
| `app.py` | Streamlit dashboard. Presentation only. |
| `pipeline.py` | All the logic: load, clean, validate, and metrics (headcount, TCC, attrition, org roll-ups). This is the single source of truth. |
| `analysis/answers.py` | Prints the case-study answers for an as-of date and writes them to `analysis/output/answers_<date>.xlsx`. |
| `analysis/verify_independent.py` | A from-scratch re-implementation of the headline numbers that doesn't import `pipeline.py`. Use it to cross-check results. |
| `data/people_data.xlsx` | The data file on record (synthetic). |

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Python 3.11+
pip install -r requirements.txt
streamlit run app.py                                     # opens http://localhost:8501
python analysis/answers.py --as-of 2026-09-01            # case answers
python analysis/verify_independent.py                    # independent cross-check
```

## Deploy free on Streamlit Community Cloud (about 5 minutes)

1. Create a new GitHub repository, for example `people-intel-dashboard`, and push this folder to it:
   ```bash
   git init && git add . && git commit -m "People Intelligence dashboard"
   git branch -M main
   git remote add origin https://github.com/<you>/people-intel-dashboard.git
   git push -u origin main
   ```
2. Go to **share.streamlit.io**, sign in with GitHub, and click **Create app → Deploy a public app from GitHub**.
3. Set the repository to your new repo, the branch to `main` and the main file path to `app.py`.
4. Open **Advanced settings** and choose **Python 3.12**. Then click **Deploy**.
5. Copy the `https://<name>.streamlit.app` URL. That link is what HRBPs open.

> The case data is synthetic, so a public repo is fine here. With real employee data you would use a private
> repo plus viewer authentication, or an internal host. See "If I had a week" in the write-up.

## Monthly refresh (no code)

- **HRBP:** open the link, upload the new export in the sidebar, and pick a leader. The as-of date defaults to the
  1st of the month after the latest record.
- **Admin:** replace `data/people_data.xlsx` in the repo. The app redeploys automatically.

## Key definitions
- **Active on date D:** hired on or before D and has no exit on or before D.
- **Org:** the leader plus everyone below them in `manager_hierarchy`, at every level.
- **TCC:** annual base (hourly × 2,080) plus annual target bonus, using the latest record effective on or before D, converted to USD at the
  `legal_entities` FX rate.
- **Attrition:** exits ÷ average daily headcount. Annualized = × 365 ÷ days in the period.
- **First year:** fewer than 365 days of tenure, measured against first-year headcount.
