# Where DeepSeek spend goes, and what was changed (2026-09-23)

Measured locally from every worker transcript in the three projects (195 runs, 11,789 API calls), so the
analysis itself cost nothing. Prices assumed at DeepSeek's list rates (cache hit $0.028, cache miss $0.28,
output $0.42 per million tokens); the shares are what matter, and the total came to about $62.

| Tokens | Amount | Share of cost |
|---|---|---|
| Cache reads (re-reading the conversation so far) | 1,813 M | **83%** |
| Output | 14 M | 10% |
| Uncached input | 17 M | 8% |

**The cost is re-reading, not thinking or writing.** Every call resends the whole conversation, which
grows as the worker reads files and command output. The fixed start is small (5k to 20k tokens); the
median call carries 137k, the 90th percentile 310k, the largest 594k. A run's cost therefore grows roughly
with the square of its length: the six costliest runs were coders at 236 to 281 calls, about $2 to $2.70
each.

| Kind and effort | Runs | Cost | Average calls |
|---|---|---|---|
| impl, max | 60 | $39.90 | 117 |
| research, max | 17 | $8.32 | 101 |
| research, high | 34 | $3.70 | 28 |
| review, max | 7 | $1.34 | 46 |
| review, high | 7 | $0.46 | 22 |

## Compaction does not happen in headless runs

Replaying the real runs with compaction near 200k suggested about 42% less re-reading. It doesn't work in
practice. `probe-023`, `probe-024` and `probe-025` set `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to 40k and 30k,
then 100k with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=30`, and read files one per step up to 47k of context:
none compacted, and the transcript has no compaction entry. The existing setting (786k) was never doing
anything either, and is left as it was. The three probes cost about a cent each.

## What was changed instead

- **Reading kinds default to effort `high`** (research, websearch, review, analysis, critic, digest,
  advisor), unless `-Effort` is given. At `max`, research averaged 101 calls and $0.49 a run; at `high`,
  28 calls and $0.11. The two groups ran different tasks, so part of that gap is the tasks; the direction
  is clear. Coders keep `max`.
- **Workers are told to keep their context lean:** search before reading, read the part of a large file
  they need, and cut long command output to what matters.
- **The skill tells Claude to keep each brief under about 100 steps and split larger ones**, since two
  half-size tasks cost about half of one big one.

Not yet measured: the effect of the lean-context note and of smaller briefs. Run `python tools/ds_cost.py <project>`
over the next week of runs to see it.
