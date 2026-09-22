# GitHub product analytics

Three product-analytics case studies on GH Archive — every public event on
GitHub, from 2011 to now.

GitHub is a real product with paying customers, and its event log is public.
That makes it one of the few places where questions like "which features do the
teams that stay actually use" can be answered on real data rather than on a
simulation or a stand-in from another industry.

The three case studies share one data model, built once:

| | Question | Page | Write-up |
|---|---|---|---|
| 1 | Activity fell a third overnight — did users leave? | [read it](https://azadvoryanskiy.github.io/github-product-analytics/) | [`docs/01-data-quality.md`](docs/01-data-quality.md) |
| 2 | What happens in a new account's first days, and who comes back? | [read it](https://azadvoryanskiy.github.io/github-product-analytics/activation.html) | [`docs/02-activation.md`](docs/02-activation.md) |
| 3 | Which features keep people on the platform? | [dashboard](https://azadvoryanskiy.github.io/github-product-analytics/features.html) | [`docs/03-features.md`](docs/03-features.md) |

Start with [`docs/data_notes.md`](docs/data_notes.md): what one row is, what the
data can answer, and what it cannot.

## Getting the data

Nothing is committed — `data/` is ignored. The events come from
[GH Archive](https://www.gharchive.org/), which is open, needs no account and
has no quotas.

```bash
pip install pyarrow orjson requests duckdb
python src/extract.py 2026-09-07:2026-09-13
```

`src/extract.py` downloads one hour at a time, keeps 15 columns, appends them to
that day's Parquet file and deletes the download. One day of events is 1.04 GB
gzipped and 56 MB once extracted, and takes about 36 seconds end to end. Peak
disk use is one hourly file plus the output, so a long run never fills the disk.

The days each case study uses are listed at the top of its write-up.

## Layout

```
src/extract.py    download GH Archive, write one Parquet file per day
src/bots.py       the automation rules
src/cohort.py     signup weeks as ranges of account id
src/activation.py the funnel and the per-newcomer feature table
src/drivers.py    what separates the newcomers who come back
src/features.py   event types grouped into features, and the retention outcomes
src/cube.py       every slice the dashboard can show, as one small JSON
src/validate.py   check those rules against the GitHub API
src/figures.py    the charts, in a light and a dark theme
notebooks/        the analyses, as jupytext .py plus executed .ipynb
docs/             the published page, the write-ups and the data notes
data/             gitignored
```

`docs/` is what GitHub Pages serves, so the published page and the write-ups it
links to sit in the same place.
