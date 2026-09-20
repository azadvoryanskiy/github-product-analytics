# The first day decides

**Question:** what happens in a new GitHub account's first days, and who comes
back?

**Answer:** two thirds never come back. What separates the third that does is
not how eager they were — it is whether they *made* something, and whether a
human answered them. Four out of five newcomers who post something get no reply
at all.

Nine weekly signup cohorts, June–July 2025. 1,526,935 newcomers.
Code: [`src/cohort.py`](../src/cohort.py),
[`src/activation.py`](../src/activation.py), [`src/drivers.py`](../src/drivers.py).
Data caveats: [`data_notes.md`](data_notes.md).

---

## Getting the cohort right came first

GH Archive never says when an account was created, and the obvious substitute —
"the first time we see them" — is badly wrong. I sampled 600 accounts first seen
in one week and asked the API when they actually registered:

| Account age when first seen | Share |
|---|---|
| Same day | 8.1% |
| 1–7 days | 0.5% |
| 8–30 days | 3.1% |
| 1–3 months | 5.4% |
| 3–12 months | 13.0% |
| 1–2 years | 12.3% |
| **2+ years** | **57.6%** |

Median age: **1,040 days**. "First seen" is overwhelmingly dormant old accounts
waking up, not newcomers. Building a cohort that way would have measured
something else entirely.

What works instead: GitHub issues `actor_id` in registration order. Sorted by
id, 370 accounts spread across 2025 had **zero** dates going backwards. So a
week of signups is a contiguous range of ids, and `src/cohort.py` finds each
boundary by binary search against the API rather than guessing it from a sample.
Checked afterwards on 12 resolvable accounts either side of all nine
boundaries: **216 of 216 fell on the correct side.**

## The funnel

| | Per week |
|---|---|
| Account ids issued | 1.0–1.3M |
| Took any public action inside 28 days | 165,000–175,000 (13.5–16.9%) |
| Came back on a second day | **33.1%** of those |

Automation is removed first, using the rules from the
[data-quality case study](01-data-quality.md) — new accounts are exactly where
the push farms live.

Two definitions worth stating:

- **28 days, not 30.** Newcomers come back on the same weekday they arrived —
  the return counts bump at days 7, 14, 21 and 28. A window that is not a whole
  number of weeks gives different cohorts different numbers of weekends.
- **A second *day*, not a second event.** Half of all newcomers fire several
  events within minutes of the first. That is one sitting, not a return.

The 33.1% holds across all nine weeks (31.4% – 34.6%), so it is not one odd
week.

## What separates them

Newcomers who do more of anything come back more often, so every comparison is
run twice: raw, and inside bands of how much the account did on day one.

| On day one they… | Share of newcomers | Raw gap | Same-volume gap |
|---|---|---|---|
| Got a reply from someone | 1.4% | +13.2 | **+12.1** |
| Pushed code | 38.4% | +16.4 | **+11.3** |
| Opened a pull request | 2.1% | +15.0 | **+10.4** |
| Commented | 1.3% | −1.7 | −2.3 |
| Forked a repository | 7.7% | −6.3 | −3.7 |
| Touched someone else's repository | 22.7% | −8.9 | −5.0 |
| Opened an issue | 2.4% | −6.8 | −6.2 |
| Starred a repository | 10.2% | −12.1 | **−8.8** |

Roughly a third of each raw gap was eagerness, not the action. What is left
still points one way: **the newcomers who make something of their own come back;
the ones who start by looking at other people's work do not.** Starring is the
clearest negative signal in the data.

Day-one volume on its own is strong and monotone: 1 event 25.9%, 2–3 events
33.0%, 4–10 events 43.5%, 11 or more 56.7%.

## The one lever that survives every check

Getting a reply is the only feature that barely shrinks when volume is matched
(13.2 → 12.1). That makes sense: how many events you fire is yours to control,
whether a stranger answers you is not.

Tested properly — only among the 80,152 newcomers who posted something a person
*could* reply to:

| Day-one events | No reply | Got a reply | Gap |
|---|---|---|---|
| 1 | 20.0% | 30.6% | +10.6 |
| 2–3 | 30.2% | 40.4% | +10.2 |
| 4–10 | 42.0% | 52.3% | +10.3 |
| 11+ | 54.9% | 63.0% | +8.1 |

Consistent in every band, odds ratio 1.39, Fisher exact p = 1.4 × 10⁻⁷⁷.

And the gap in coverage is enormous: **only 21.2% of newcomers who posted
something got any reply at all**, and only 5.2% of newcomers post anything
repliable in the first place.

---

## What I would change

**Route a first-time contributor's first post to a human within 24 hours.**
That is the intervention: a maintainer nudge, a triage queue, a first-timer
label — whatever gets an answer in front of them. The candidates are already
identifiable at the moment they post, because `author_association` is `NONE` and
the account id says they registered this week.

**Stop treating stars and forks as onboarding progress.** They are the strongest
*negative* signal here. A newcomer who has only starred things is not warming
up; they are on the way out. Any "getting started" flow that counts those as
steps completed is measuring the wrong thing.

**Push the first flow toward making something.** Pushing code on day one is
worth +11.3 points and reaches 38% of newcomers — by far the widest lever in
this data.

## How I would test it

Randomise newcomers who post something on day one and receive no reply within
some hours; treatment gets the post surfaced to a maintainer.

- Population: ~7,000 such newcomers a week
- Baseline: 33.3% come back on a second day
- The observed gap is 8–10 points, but that is correlational, so plan for less

| Effect to detect | Per arm | Weeks of newcomers |
|---|---|---|
| +2 points | 8,843 | 2.5 |
| **+3 points** | **3,956** | **1.1** |
| +5 points | 1,442 | 0.4 |

At +3 points the test reads out in about two weeks including both arms. That is
cheap enough that the bigger risk is shipping it untested.

---

## Caveats

- **The top of the funnel is an estimate.** Accounts that sign up and never act
  are invisible here, so "13.5–16.9% take an action" rests on id ranges standing
  in for signups. Ids also go to organisations and some are never used, so the
  denominator is an upper bound and the percentage a lower one.
- **The reply effect is correlational.** A newcomer who posts something
  interesting is more likely to get a reply *and* more likely to come back. The
  banding removes the volume part of that, not the quality part. This is exactly
  why the recommendation comes with a test rather than a claimed lift.
- **Public activity only.** Someone who spent their first week in a private
  repository looks identical to someone who vanished.
- **One season.** June and July 2025 only. Student intakes in September, or the
  January wave, may behave differently.
