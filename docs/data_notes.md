# Data notes — GH Archive

What the data is, what it can and cannot answer, and the decisions the three
case studies in this repo are built on. Every number below was measured, not
estimated; the command that produced it is named where it matters.

## One row is one event

GH Archive records every public event on GitHub and publishes it as one
gzipped JSON file per hour. Here is a real row, from `2026-09-15-15.json.gz`,
with the long fields trimmed:

```
id:         15078458244
type:       PullRequestEvent
actor:      NuwangaNiroshan (id 247282152)
repo:       SanchiaLakkarvi/3D-printer-farm-interface (id 1312720501)
payload:    action = "merged", number = 66,
            head = feature/printer-material-api-gaps, base = main
created_at: 2026-09-15T15:00:00Z
```

Someone, something they did, the thing they did it to, and when. That is the
same shape product events take in Mixpanel or Amplitude — `user_id`,
`event_name`, `properties`, `timestamp` — except this is a real product used by
millions of people rather than a demo project.

## How much there is

Measured on 15 September 2026, a Tuesday:

| | |
|---|---|
| Events in the day | 1,789,869 |
| Download size, gzipped | 1.04 GB |
| Unpacked JSON | ~5 GB |
| After extraction (Parquet, zstd) | 56.3 MB |
| Time to download and extract one day | 36 s |

The 98% reduction is almost entirely one field. In the 15:00 UTC hour the file
is 296 MB unpacked, and `payload` alone is 256 MB of it — **86% of all bytes
are issue and comment text**, which none of these analyses read. Dropping it is
what makes the whole thing run on a laptop.

That single hour holds 81,142 events from 30,426 accounts across 37,882
repositories.

## The event types are the product's features

Counts from the 15:00 UTC hour on 15 September 2026:

| Event | Count | What it is in the product |
|---|---|---|
| PushEvent | 24,180 | pushed code |
| PullRequestEvent | 19,423 | opened or merged a pull request |
| IssueCommentEvent | 9,674 | commented on an issue or PR |
| IssuesEvent | 7,184 | opened or closed an issue |
| PullRequestReviewEvent | 5,811 | reviewed a pull request |
| PullRequestReviewCommentEvent | 4,777 | commented inside a review |
| WatchEvent | 3,933 | starred a repository |
| CreateEvent | 2,133 | created a repository, branch or tag |
| ReleaseEvent | 1,583 | published a release |
| ForkEvent | 900 | forked a repository |
| DeleteEvent | 777 | deleted a branch or tag |
| MemberEvent | 373 | added or removed a collaborator |
| CommitCommentEvent | 169 | commented on a commit |
| PublicEvent | 96 | made a private repository public |
| GollumEvent | 85 | edited the wiki |
| DiscussionEvent | 44 | used Discussions |

## Traps in the field names

**`WatchEvent` is a star, not a watch.** The name is a leftover from an old
version of the GitHub API. All 3,933 `WatchEvent` rows in the sample hour carry
`payload.action = "started"`, and there is no other value. Reading it as
"subscribed to notifications" would be wrong.

**`closed` and `merged` are different actions.** In the sample hour
`PullRequestEvent` splits into opened 7,602, merged 6,463, labeled 4,111,
closed 451, unlabeled 372, assigned 354, reopened 68, unassigned 2. A pull
request that was merged never appears as `closed`, so counting `closed` as
"finished" undercounts by more than ten to one.

**The payload is not symmetric.** In 2026 the `issue` object arrives complete —
author, body, timestamps, comment count. The `pull_request` object is stripped
to `base`, `head`, `id`, `number`, `url`. So the author and the age of an issue
can be read straight from the event, and the same facts about a pull request
cannot. `src/extract.py` records both as NULL where they are missing rather
than filling them in.

## The payloads were cut on 7 October 2025

GitHub [announced on 8 August 2025](https://github.blog/changelog/2025-08-08-upcoming-changes-to-github-events-api-payloads/)
that it was shrinking the Events API payloads, and did it on 7 October 2025.
The difference is large:

| | Before 7 Oct 2025 | After |
|---|---|---|
| Fields on `pull_request` | 48 | 5 |
| `author_association` | present | gone |
| `merged`, `merged_at`, `merged_by` | present | gone |
| `additions`, `deletions`, `changed_files` | present | gone |
| Commit list and count on `PushEvent` | present | gone |
| `DiscussionEvent` | absent | present |

`author_association` is the one worth caring about. It is GitHub's own label
for how the author relates to the repository — `NONE`, `CONTRIBUTOR`,
`COLLABORATOR`, `MEMBER`, `OWNER` — so who is an outsider does not have to be
inferred. On 11 June 2025, 27,745 pull requests were opened by accounts with
`NONE`.

The same hour on 15 September **2015** has 42,519 events and `PullRequestEvent`
takes only three values: closed 1,254, opened 1,178, reopened 25. No `merged`,
no `labeled`. So the share of pull requests that were merged cannot be computed
for 2015 at all, and a chart putting 2015 beside 2024 on that metric is
comparing a definition with its own absence.

## The feed was capped on 24 May 2025

Daily events went from 5.02M on 23 May to 3.42M on 24 May and stayed there. It
is not behaviour: every event type fell by about the same third, every kind of
account fell by about the same third, and no hour of any day after 24 May
carries more than about 169,000 events where the busiest hours before it
carried 251,000–281,000.

The cap keeps 58% of events at the busiest hour and 75% at the quietest, so the
data after it is not a random sample — it under-represents busy hours, and with
them the most active users.

**Decision: no analysis window may span 24 May 2025.** The case studies that
need a cohort and a follow-up use days from 26 May 2025 onwards.

## 2026 is not usable

The feed degrades through 2026. Share of all events that are `PushEvent`, one
Wednesday per month:

```
Jan 2026  67%     Jun 2026  85%     Aug 2026  96%
Mar 2026  73%     Jul 2026  94%
```

For the ten years before that it sat between 47% and 64%. By August 2026 there
is almost nothing in the feed except pushes. Individual days fail outright: on
19 August 2026 the feed ran normally until 15:00 UTC and then dropped to about
a thousand events an hour; on 2 September 2026 the whole day carries 45,971
events and not a single push.

**Decision: all three case studies use 2025 data and say so.** The 2026
breakage is evidence in the data-quality case study, not a foundation for
anything else.

## Sampled days must share a weekday

Activity swings by more than a third between a Wednesday and a Sunday. A series
built from one 15 September per year compares 2018 (a Saturday) with 2023 (a
Friday) and measures the calendar as much as it measures GitHub. Every sampled
series here holds the weekday fixed.

## Identity

`actor.login` is the account's name *at the time of the event*, and people
rename accounts. `actor.id` never changes. Everything here keys on `actor.id`
and treats the login as a label. Measured over 70 days in 2025, that is not a
theoretical concern:

- **1,015 logins were used by two different accounts**, a few by as many as
  six. Two separate accounts both posted as `Copilot`. A join on the login
  merges them into one.
- **More than 62,000 accounts changed their login inside the window.** Keyed on
  the login, each looks like one user leaving and another arriving.

There is no registration date in the archive. `actor.id` is issued in
registration order, which makes it a usable proxy for account age: in the
sample hour it runs from 103 (an account from GitHub's first days) to
329,625,442, with the median at 105,283,953. Turning an id into an approximate
date needs calibration against the GitHub API on a sample of accounts; that is
done in the activation case study, not here.

## What this data cannot answer

- **No money.** Who pays for GitHub is not visible, so no pricing, LTV or
  trial-to-paid questions.
- **No private repositories.** Only public activity. Teams that work in private
  are invisible, and that is a real selection bias, not a rounding error.
- **No passive use.** Reading code, browsing, searching — none of it is an
  event. Only actions that change something get recorded.
- **No signups.** An account that registers and never does anything public
  never appears. Any funnel here starts at the first action, not at signup.
- **Events, not state.** The archive says what changed, never what exists. The
  number of repositories on GitHub cannot be read off it.

## Missing hours

GH Archive has gaps where GitHub's own API was down. `src/extract.py` treats a
404 on an hour as data rather than as a failure: it reports the missing hour
and carries on, so a day with a gap is still usable as long as the gap is
stated.

## What the extraction keeps

`src/extract.py` downloads one hour, keeps 15 columns, appends them to that
day's Parquet file and deletes the download, so peak disk use is one hourly
file plus the output. The columns are `event_id`, `event_type`, `created_at`,
`actor_id`, `actor_login`, `repo_id`, `repo_name`, `org_id`, `org_login`,
`action`, `ref_type`, `pusher_type`, `target_number`, `target_author`,
`target_created_at`.

`created_at` is stored as TIMESTAMP WITH TIME ZONE. DuckDB then renders it in
the session's timezone, so on a laptop in Calgary every event silently moves
six hours back, each UTC day splits across two local dates, and a complete day
looks like it is missing six hours. `src/data.py` pins every connection to UTC.

The list is deliberately wider than any one case study needs. Re-downloading
three months to add a column costs an hour; carrying a few extra columns costs
nothing next to the payload text that was dropped.
