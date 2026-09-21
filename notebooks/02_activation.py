# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # The first day decides
#
# A million people a week open a GitHub account. This notebook asks what happens
# in their first four weeks, and what separates the ones who stay.
#
# Most of the work is not the answer. It is making sure the question is being
# asked of the right people — the obvious way to define "a newcomer" turns out
# to be wrong by about three years.

# %%
import sys
sys.path.insert(0, "../src")

import pandas as pd
from scipy import stats

import activation_figures as figs
import charts
import drivers as drv
from bots import PROCESSED
from cohort import BOUNDARIES, OBSERVATION_DAYS
from data import connect

theme = charts.use("light")
con = connect()
drv.load(con)          # one row per newcomer: day-one features, later outcome
frames = figs.load()

# %% [markdown]
# ## 1. Who counts as a newcomer?
#
# GH Archive records events, not signups. There is no registration date in it
# anywhere.
#
# The obvious substitute is "the first time this account appears in our data".
# Before building anything on that, I took 600 accounts that first appeared in
# one week and asked GitHub's API when each was actually created.

# %%
sample = frames["sample"]
print(f"{len(sample)} accounts resolved")
sample.age_days.describe(percentiles=[0.25, 0.5, 0.75]).round(0).to_frame("days old")

# %% [markdown]
# **The median "newcomer" had held the account for 1,040 days.** Only 8% were
# made that day.
#
# So "first seen" mostly finds dormant accounts waking up. Building a cohort
# that way would have measured something completely different, and nothing
# downstream would have looked wrong.

# %%
figs.account_ages(sample, theme);

# %% [markdown]
# ## 2. The fix: account ids are queue tickets
#
# GitHub hands out `actor_id` in registration order. If that holds, a week of
# signups is simply a range of ids — and the range can be found exactly instead
# of guessed.
#
# Checked on 370 accounts spread across 2025: sorted by id, how many times does
# the registration date go *backwards*?

# %%
cal = pd.read_parquet(PROCESSED / "id_calibration.parquet").sort_values("actor_id")
print(f"{len(cal)} accounts checked")
print(f"dates going backwards: {(cal.created_at.diff().dt.days < 0).sum()}")

# %% [markdown]
# Zero. So `src/cohort.py` binary-searches the API for the first id issued on
# each Monday, which pins the boundary exactly rather than to within a sample's
# resolution.

# %%
pd.read_parquet(BOUNDARIES)

# %% [markdown]
# ### Then check the boundaries, rather than trusting them
#
# For every boundary I pulled 12 resolvable accounts just below it and 12 just
# at or above it, and asked whether each was created on the right side.
#
# **216 of 216 were correct.** The cohorts are exact.

# %% [markdown]
# ## 3. The funnel
#
# One clock for everyone: days since the Monday their account was made.
# Automation is stripped out first with the rules from the data-quality case
# study — new accounts are exactly where the push farms live.
#
# Two definitions worth saying out loud:
#
# * **28 days, not 30.** Returns bump on days 7, 14, 21 and 28 — people come
#   back on the weekday they arrived. A window that is not whole weeks gives
#   different cohorts different numbers of weekends.
# * **A second *day*, not a second event.** Half of all newcomers fire several
#   events within minutes of their first. That is one sitting, not a return.

# %%
weekly = frames["weekly"]
weekly

# %%
figs.funnel(weekly, theme);

# %% [markdown]
# Of the people who do anything at all, **a third come back on a second day** —
# and that number holds across all nine weeks (31.4% to 34.6%), so it is not one
# odd week.

# %% [markdown]
# ## 4. What separates them — and the trap
#
# The obvious move is to compare people who did X against people who did not.
# The trap is that eager newcomers do more of *everything* and come back more
# often, so every feature looks helpful.
#
# So each comparison is run twice: raw, and again inside bands of how much the
# account did on its first day.

# %%
con.sql("""
    SELECT band AS day_one_events, count(*) AS accounts,
           round(100.0 * avg(came_back::INT), 1) AS came_back_pct
    FROM newcomers GROUP BY 1 ORDER BY min(events)
""").df()

# %%
gaps = frames["gaps"]
gaps

# %%
figs.driver_gaps(gaps, theme);

# %% [markdown]
# Roughly a third of every raw gap was eagerness rather than the action. What
# survives still points one way:
#
# **Newcomers who make something come back. Newcomers who look at other people's
# work do not.** Starring is the strongest negative signal in the data — which
# means any "getting started" flow that walks people around to explore and star
# things is walking them toward the exit.

# %% [markdown]
# ## 5. The one lever that barely shrinks
#
# Getting a reply is the only feature that survives matching almost intact
# (+13.2 raw, +12.1 matched). That makes sense: how many events you fire is
# yours to control, whether a stranger answers you is not.
#
# Tested properly — only among newcomers who posted something a person *could*
# reply to, because comparing against everyone else would mostly compare posters
# with non-posters.

# %%
con.sql("""
    SELECT posted_something, count(*) AS accounts,
           round(100.0 * avg(got_a_reply::INT), 1) AS got_a_reply_pct
    FROM newcomers GROUP BY 1 ORDER BY 1
""").df()

# %% [markdown]
# Only 5.2% of newcomers post anything repliable at all — and of those, **only
# one in five gets an answer.**

# %%
table, odds, p = drv.reply_effect(con)
print(f"odds ratio {odds:.2f}, Fisher exact p = {p:.1e}")
table

# %%
figs.reply_effect(table, theme);

# %% [markdown]
# Consistent in every band: +10.6, +10.2, +10.3, +8.1 points. The effect is not
# an artefact of eager people getting more replies.

# %% [markdown]
# ## What I would change
#
# **Route a first-time contributor's first post to a human within 24 hours.**
# They are identifiable the moment they post: `author_association` is `NONE` and
# the account id says the account is days old. A maintainer nudge, a triage
# queue, a first-timer label — whatever gets an answer in front of them.
#
# **Stop counting stars and forks as onboarding progress.** They are the
# strongest negative signal here.
#
# **Point the first-run flow at making something.** Pushing code on day one is
# worth +11.3 points and reaches 38% of newcomers — the widest lever in this
# data.
#
# ### How I would test it
#
# Randomise newcomers who post on day one and get no reply within a few hours;
# treatment surfaces the post to a maintainer. The observed gap is 8–10 points,
# but it is correlational, so plan for less.

# %%
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize
import math

base, weekly_eligible = 0.333, 63179 / 9
rows = []
for lift in (0.02, 0.03, 0.05):
    n = math.ceil(NormalIndPower().solve_power(
        effect_size=proportion_effectsize(base + lift, base),
        power=0.8, alpha=0.05, ratio=1, alternative="two-sided"))
    rows.append({"detect": f"+{lift*100:.0f} points", "per arm": n,
                 "weeks of newcomers": round(2 * n / weekly_eligible, 1)})
pd.DataFrame(rows)

# %% [markdown]
# At +3 points the test reads out in about a week and a half of newcomers. That
# is cheap enough that the bigger risk is shipping the change untested.
#
# ### What this does not show
#
# The reply effect is **correlational**. A newcomer who posts something
# interesting is more likely to get a reply *and* more likely to come back; the
# banding removes the volume part of that, not the quality part. That is exactly
# why the recommendation ends in a test rather than a promised lift.
#
# The top of the funnel is an estimate — accounts that sign up and never act are
# invisible here, so id ranges stand in for signups. And this is June and July
# only; a September student intake may behave differently.
