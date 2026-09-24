# Spend limits

The user asked (2026-09-24, with their DeepSeek credit running low after a heavy week) for a spend limit
that works like Claude's usage limits: check the credit, estimate what the work will cost, and fit it
within a daily or weekly budget.

## What it does

`launcher/ds_spend.py`, called by `ds-agent.ps1`, so it covers every way a worker starts (Claude,
`ds-spawn.ps1`, a lead's `spawn_workers`, `ds_impl.ps1`).

- **Before a worker starts** (`check`): for each limit set (day, week, or both), spent = runs recorded
  in the current window + what running workers have spent so far. The worker is refused (exit 4, a
  plain reason and the reset time) when the limit is used up, or when its kind's estimate does not fit
  in what is left. It is also refused when the DeepSeek balance, which the key check already fetches, is
  below the estimate. From 80% used, the launch goes ahead with a warning.
- **While it runs** (`live`, every 15 seconds): the worker's spend so far goes to `live/<run id>.json`,
  so parallel workers and a lead's children all see each other's spend. When the total reaches a limit,
  the launcher stops the worker, keeps its partial report (the timeout path), records it as `canceled`
  and exits 4.
- **When it ends** (`record`): one line in `spend.jsonl`, and the manifest gets `cost_usd`.

The folder is per user, not per project (`~/.claude-deepseek/spend`, or `DS_SPEND_DIR`, which the
launcher passes on to a lead's workers), because the credit is shared. Windows are calendar ones: local
midnight, and Monday midnight for a week. There is no limit until the user sets one.

**Estimates** are the mean cost of the kind's last 20 recorded runs once there are 3, else a table
from 233 past runs (impl $0.70, lead $0.60, analysis $0.40, research $0.25, review $0.15, websearch
$0.05). The mean rather than the median, because the cost of coders has a long tail.

**Costs** are the transcript's token counts at DeepSeek list prices, the same numbers as
`tools/ds_cost.py`. Against the DeepSeek dashboard they came out roughly a third higher in the one
comparison made, so limits act a little early rather than late. The dashboard is the real bill.

## Pacing

A limit alone lets a busy morning spend the whole day's budget, and then everything stops. So spending
is paced, as ad budgets are: at any moment the on-pace amount is the share of the window gone by plus a
head start of 20% of the limit, and each launch compares (spent + this worker's estimate) with it.

| Ratio | Step | What changes |
|---|---|---|
| up to 1 | on pace | nothing |
| over 1 | 1 | effort capped at high; the worker is told to finish in few steps; delegation reads one level lower |
| over 1.25 | 2 | effort low; one worker at a time: a new worker waits (up to 20 minutes) for running ones, except its own ancestors |
| over 1.5 | 3 | as 2, and coders and leads are refused, with the time they fit the pace again |

Effort goes first because it is the cheapest thing to give up; the lower delegation level makes Claude
hand off less, which is the biggest lever of all (83% of spend is re-reading context in long runs). A
lock (`pace.lock`) makes workers started together, such as a lead's `spawn_workers`, take turns to
check and claim their place. Step 3 can only happen in the first half of a window: later, a ratio
of 1.5 is already past the limit itself, and the hard limit takes over.

## Limits of the design

- The check runs every 15 seconds, so a worker can overshoot by up to 15 seconds of spend (well under a
  cent for one worker; several parallel workers each overshoot a little).
- A worker killed from outside (Ctrl+C on the launcher) is not recorded; its live file is dropped once
  its launcher's process is gone.
- Only a USD balance is compared; a CNY account skips the balance check.

## Evidence

- `probe-026-spend-refused` (limit $0.01, $0.02 recorded): refused before starting, exit 4, no spend:
  "DeepSeek spend limit reached: $0.02 of $0.01 today. It resets at 00:00 (in 10h 51m). Do this work
  yourself, or ask the user to raise the limit".
- `probe-027-spend-stop` (limit $0.04, $0.03 recorded): started with the warning "100% of the daily
  DeepSeek limit will be used once this worker is done"; finished in 18 s, before the first 15-second
  check, and recorded $0.0116 (113,792 cache-read, 25,979 fresh, 2,606 out). Status then read 103%.
  This is the overshoot case above.
- `probe-028-spend-stop` (limit $0.035, $0.033 recorded, so the estimate fit): the first 15-second
  check found the limit reached and stopped the worker at 16 s. The manifest reads `canceled`, "stopped
  at the spend limit: the daily DeepSeek spend limit ($0.04) is used up; it resets at 00:00"; the
  report kept its partial text; $0.0085 was recorded, the live file was cleared, and the launcher
  exited 4.
- Pacing, limit $10/day with $9.50 recorded at 13:19 (step 2), `-Effort max` passed:
  `probe-029`/`probe-030` both ran at effort low ("effort max runs as low while DeepSeek spending is
  ahead of pace"). They did not wait for each other: 029 took 2 s and had finished and cleared its claim
  before 030 checked. `probe-031` (21 s) and `probe-032`, started 6 s later: 032 printed "Waiting for
  the other DeepSeek workers to finish", and started at 13:20:42, after 031 ended at 13:20:33 (its next
  10-second check). `ds_delegation.py --brief` read "level 3 ... (lowered from 4 while DeepSeek spending
  runs ahead of the pace ...)" against that spend folder and level 4 without it. Step 3 is covered by
  the unit tests only: at 13:00 it cannot occur (see above).
