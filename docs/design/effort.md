# Effort: how long a worker thinks

## What reaches DeepSeek

`ds-agent.ps1 -Effort <level>` sets `CLAUDE_CODE_EFFORT_LEVEL`. Claude Code (2.1.275) passes it straight into
every request as `output_config.effort`, with `thinking: {"type": "adaptive"}` and, by default,
`max_tokens: 32000`. This was captured with a local stand-in server (`experiments/capture_request.py`), for
low, medium, high, xhigh and max.

DeepSeek has three levels. Its thinking-mode docs map requested values: minimal/low to **low**, medium/high
to **high**, and xhigh/max/ultra to **max**, with `none` turning thinking off
(api-docs.deepseek.com/guides/thinking_mode). The launcher now does that mapping itself: `medium` and
`xhigh` are still accepted, but they are sent as `high` and `max`, and the manifest records `effort` (what
ran) and `effort_requested`.

## Does the level change anything? Yes, on hard problems

`experiments/effort_api_probe.py` calls the API directly (`local/experiments/effort-api*.txt`):

| Problem | Cap | low | high | max |
|---|---|---|---|---|
| Easy (digit sums below 100000; answer 6000) | 32k | ~300-400 tokens, right | - | ~400-500 tokens, right |
| Hard (permutations of 1..8 with no fixed point and no rising pair; answer 5484), 2 runs each | 32k | **hit the cap, no answer** (both runs) | hit the cap, no answer | hit the cap, no answer |
| Same hard problem, 1 run each | 128k | 24,033 tokens, **5242 (wrong)** | - | 107,138 tokens, **5484 (right)** |

- On easy work the level barely matters: every level answers quickly and correctly.
- On hard work `max` thought about 4.5 times as long as `low` and was right where `low` was wrong. That is one
  run each: treat the ratio as rough, but the direction as settled.
- `output_config.effort` (what Claude Code sends) and `reasoning.effort` (what DeepSeek documents) behaved the
  same on the easy problem.

## The 32k cap was cutting hard steps off

With Claude Code's default `max_tokens` of 32000, all six hard-problem runs spent the whole budget thinking
and returned nothing. The correct answer needed 107k. The launcher now sets
`CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`, the most Claude Code will send (384000 was captured as 128000).
DeepSeek Flash allows 384k output.

## Through a real worker: reasoning alone ran away; tools fixed it

| Run | Setup | Result |
|---|---|---|
| `probe-hard-max.1` | same hard problem, `max`, 128k cap, **no tools** | two steps of 127,999 and 128,000 tokens, all thinking, no answer; stopped at its 25-minute limit (recorded `timed_out`) |
| `probe-hard-tools.1` | same problem, `max`, allowed to write and run a Python file | **5484, right**, in 12 turns and 44k output tokens, checked three independent ways |

Through Claude Code the no-tools worker needed more than 128k where the direct API call had needed 107k: the
amount of thinking varies a lot between runs, and a step cut off at the cap seems to start its reasoning over.
The lesson is not "use less effort" but "let the worker compute": a brief for anything numeric or
algorithmic should allow writing and running a script (`-Mode edit -AllowTools "Bash(python *)"`; inline
`python -c` is always denied for workers).

## Choosing a level

| Level | Use for |
|---|---|
| `low` | mechanical work with an obvious method: renames, formatting, copying a pattern, simple lookups |
| `high` | ordinary research, reviews, bounded code with a clear spec; the default for a lead's workers |
| `max` | hard reasoning (debugging, algorithms, maths, reverse engineering) and anything where a wrong answer is expensive; the launcher's default |

The advisor-loop skill's quick advisor used `medium`, which always ran as `high`. It now says `high`.
