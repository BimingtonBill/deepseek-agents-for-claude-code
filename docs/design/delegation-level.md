# The delegation level (0-10)

A single number saying how much work Claude hands to DeepSeek workers: 0 = never, 10 = everything.
The scale and its rules live in one place, `tools/ds_delegation.py` (`--table` prints them), and the
skill's SKILL.md repeats the table.

## Setting it

```
python tools/ds_delegation.py                      # effective level here, and where it comes from
python tools/ds_delegation.py --set 7 --agents-md  # this project, plus the rule block in its AGENTS.md
python tools/ds_delegation.py --set 4 --global     # your default for every project
DS_DELEGATION=0                                    # this shell only, overrides everything
```

Precedence: `DS_DELEGATION`, then `"delegation"` in the project's `.deepseek-agents.json`, then
`~/.claude-deepseek/config.json`, then 5.

## Why AGENTS.md matters

The level steers **Claude**, not the workers, and Claude follows only what it sees. The skill carries the
table, but it loads only when workers come up. Without the AGENTS.md block, a project set to 8 behaves
like 1 until someone mentions DeepSeek. `--agents-md` writes a generated block (between
`<!-- ds-delegation:begin -->` and `<!-- ds-delegation:end -->`) under the file's first heading, and replaces
it on the next `--set`. Everything else in AGENTS.md is left alone.

## What is enforced, and what is guidance

- **Enforced:** level 0. `ds-agent.ps1` refuses to launch, and nothing is started or logged, unless given
  `-Force` (the user asked for that worker). Every run's manifest records `delegation` and `forced`, so a
  project's history shows which level its runs were launched under.
- **Guidance:** levels 1-10 describe what Claude delegates. No launcher can judge whether a task "could be
  briefed". The rules are written so Claude can apply them in the moment.
- **Never scaled down:** at every level Claude keeps the conversation with the user, design decisions,
  integration, security-sensitive work, and review of every worker result it acts on. DOA's record
  (0 of 9 implementations accepted without correction) is why the review floor doesn't move with the dial.

## Where the existing projects sit

DOA Xbox360 UI and OpenSkyrim both describe, in prose, research, reviews, analyses and a bounded
implementation pilot, with "minimize Claude's load" and parallel producers. That is about **6**. Neither has
a `delegation` key yet, so both currently read as the default 5.
