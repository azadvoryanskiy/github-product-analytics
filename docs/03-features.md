# Which features keep people?

**Question:** which parts of the product should we push people toward?

**Answer:** almost none of them, individually. Every feature looks like it helps
until you compare people who were active the same number of days — then most of
the gaps collapse and two of the widest go negative. The relationship that
survives is **how many** features someone uses, not which.

Dashboard: [azadvoryanskiy.github.io/github-product-analytics/features.html](https://azadvoryanskiy.github.io/github-product-analytics/features.html)
Baseline month 26 May – 24 June 2025, 5,953,160 accounts, followed 30/60/90 days.
Code: [`src/features.py`](../src/features.py), [`src/cube.py`](../src/cube.py).

---

## The population

Everyone with at least one event in the baseline month, minus the automation
caught in the [data-quality case study](01-data-quality.md). The median account
produced 3 events and was active on 3 days — a long tail sits on top of a very
large group of people who barely show up.

Retention is checked over the fortnight *ending* at each horizon, not on a
single day, because one day is mostly noise — a person on holiday is not a
person who left.

| Still active after | Share |
|---|---|
| 30 days | 30.0% |
| 60 days | 26.2% |
| 90 days | 25.3% |

## Adoption is enormously uneven

| Feature | Share of accounts |
|---|---|
| Push code | 62.0% |
| Branches and repos | 53.3% |
| Stars | 22.8% |
| Pull requests | 12.4% |
| Forks | 9.2% |
| Comments | 7.4% |
| Issues | 6.2% |
| Code review | 3.4% |
| Collaborators | 3.0% |
| Releases | 1.6% |
| Wiki | 0.3% |

Two features cover most of the product's use. Everything collaborative is a
minority activity.

## The part that matters

Compare people who used a feature against everyone else, and every feature
looks like a retention driver. Then hold activity constant — the same number of
active days in the baseline month — and re-run it.

| Feature | Raw gap | Matched gap |
|---|---|---|
| Code review | +39.0 | **+12.8** |
| Stars | +10.6 | +7.9 |
| Comments | +24.4 | +6.3 |
| Pull requests | +21.6 | +5.1 |
| Releases | +25.6 | +4.9 |
| Issues | +20.1 | +3.5 |
| Wiki | +21.4 | +2.8 |
| Forks | +4.4 | −0.3 |
| Push code | +11.5 | **−2.7** |
| Collaborators | +4.9 | −3.5 |
| Branches and repos | −0.3 | **−5.9** |

Percentage points of 90-day retention. Pushing code — the thing 62% of accounts
do — is worth *less than nothing* once you account for how active the person
was. So is creating repositories and branches. They are what everybody does, so
doing them says nothing about you.

**This is the whole argument for the dashboard.** The switch that turns matching
on is the point of the page: a manager can watch +39 become +12.8 and understand
in one click why the raw number was not an answer.

## What actually survives: breadth

| Features used in the month | 90-day retention |
|---|---|
| 1 | 19.5% |
| 2 | 23.8% |
| 3 | 34.8% |
| 4 | 45.9% |
| 5 or more | 67.5% |

Monotone, and it does not collapse under any cut on the dashboard. Whatever the
mechanism — people who find more uses for a tool have more reasons to return —
this is a far stronger signal than any single feature.

## A contradiction worth explaining

In the [activation case study](02-activation.md), starring repositories was the
*worst* signal for a newcomer: −8.8 points on coming back the next day. Here,
across all accounts, starring is a **positive** +7.9.

Both are right, and the difference is the population. For someone on their first
day, starring instead of building is a sign they came to browse. For an
established account, starring is a sign of staying plugged into the ecosystem.
A metric is not a fact about a feature; it is a fact about a feature *and* the
people being measured.

## What I would change

**Stop asking which feature to push.** Once activity is held constant, no single
feature is worth more than about thirteen points, and the two widest ones go
negative.

**Aim at the second and third feature.** One feature retains at 19.5%, five at
67.5%. That is where the leverage is.

**Code review is the one single feature worth a real try.** +12.8 matched — the
largest of any — and only 3.4% of accounts touch it. The widest gap on the page
between what something is worth and how many people reach it.

## How I would test it

Take accounts that have used exactly one feature for a month and prompt the
second — a review request, a first issue, a release. Outcome is 90-day retention
against a held-out control. The matched gaps above are correlational: they set
the ceiling, not the expectation.

---

## Caveats

- **Matching on active days removes the crudest confounder, not every one.**
  People who review code differ from people who do not in ways this data cannot
  see. Nothing here is causal.
- **Discussions is missing on purpose.** GitHub did not publish those events
  until after this window, so the feature would have drawn an empty bar and read
  as "nobody uses Discussions" rather than "this feed cannot see it".
- **Accounts are not people.** One person may hold several.
- **Public activity only**, and one season only — the baseline month is a
  northern-hemisphere early summer.
