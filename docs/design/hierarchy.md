# Goal 3 - Hierarchy: Claude, then a DeepSeek lead, then its workers

**Question.** Can the structure be Claude at the top, then a DeepSeek lead that launches its own
sub-agents, with reports flowing back up?

**Answer: yes, two ways, both tested 2026-09-21.** Use the process tier (`-CanSpawn`) for real work,
because every node gets its own manifest record, permissions and transcript. Use in-process subagents
(`-SubAgents`) for quick fan-out inside one worker.

```
Claude (you, the top lead: plans, reviews, integrates)
`-- lead-004-ui-audit.1              DeepSeek lead, depth 1, launched with -CanSpawn
    |-- research-085-radial.1        DeepSeek worker, depth 2, launched by the lead
    |-- research-086-pause-menu.1    (can message its siblings with -Crosstalk)
    `-- review-087-radial-notes.1
```

## Tier A: process leads (`-CanSpawn`)

A worker started with `-CanSpawn` gets two MCP tools from `launcher/ds_mcp.py`:

- `write_brief(name, content)` saves a brief into `runs/<lead run id>/briefs/`. The name must be
  `<kind>-<slug>`, and the brief must have a `# Goal` section.
- `spawn_workers(briefs, crosstalk?, effort?, max_turns?)` runs `launcher/ds-spawn.ps1`: up to 6 workers in
  parallel, read-only, in the lead's working folder. It waits for all of them and returns each report under
  its run id.

Lineage flows through environment variables that ds-agent.ps1 sets for every worker (`DS_RUN_ID`,
`DS_ROOT_RUN`, `DS_LINEAGE`, `DS_DEPTH`, `DS_MAX_DEPTH`, `DS_STATE_DIR`, `DS_PARENT_MODE`). A child's
manifest names its parent, and every child writes to the top lead's manifest, so
`python tools/ds_manifest.py --tree` shows the whole tree.

**Guards**

- Depth: Claude's workers are depth 1. `-MaxDepth` defaults to 2: a lead at depth 1 may spawn, a worker at
  depth 2 may not, and nothing starts at depth 3. The launcher enforces this, not the model.
- A read-only lead cannot start editing workers (`DS_PARENT_MODE`). Children are read-only by default.
- At most 6 children per `spawn_workers` call.
- Children inherit nothing from the lead's conversation. Each brief must stand alone, and the tool checks
  that it has a Goal.
- Timeouts: the lead's `MCP_TOOL_TIMEOUT` equals its own `-TimeoutMinutes`, so a long spawn isn't cut off.

**Evidence**

| Run | Result |
|---|---|
| `lead-probe-hierarchy.1`, `.2` | **Blocked.** Both tried shell-based spawning. The Bash allow rule never matched a command with quoted, spaced paths, and `Write(...)` isn't a valid file rule (Claude Code uses `Edit(...)`). Good behaviour: both leads stopped and reported instead of working around the denials (though `.1` tried three shell redirects first). This is why spawning became an MCP tool. |
| `lead-probe-hierarchy.3` | **Worked.** Two briefs written, `research-three-backwards.1` and `research-seventeen-sum.1` spawned with crosstalk, both correct (`ammag`, `72`). The lead checked both answers against the files and reported up, citing run ids. 8 turns for the lead, 5 each for the workers. |
| Dry runs | `-CanSpawn` at depth 2: refused. Any launch at depth 3: refused. |

## Tier B: in-process subagents (`-SubAgents`)

Adds Claude Code's own `Agent` tool to the worker. Subagents run inside the worker's process on the same
provider. The launcher sets `CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash` and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`,
so a subagent asked for "opus" can't reach DeepSeek's more expensive Pro model. It also sets
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, so subagents can't nest further.

**Evidence.** `probe-subagents.1` started two named subagents in parallel. Both answered correctly, and the
worker checked each against the file. All 37 model calls in its and its subagents' transcripts went to
`deepseek-flash`. The run's own usage figure (5k tokens in) left out the subagents' ~15k, so the launcher
now sums subagent transcripts into `subagent_tokens_in/out` in the manifest.

**Trade-offs.** Subagents have no manifest record, no run id, no messaging name of their own (a message from
one arrives under the parent's name) and no separate permissions. Use them for short lookups the worker
checks itself. Use Tier A when the parts deserve their own review.

## Why only two levels by default

- Anthropic's multi-agent research system (anthropic.com/engineering/multi-agent-research-system) is
  orchestrator plus workers, one level. It beat a single agent by about 90% on breadth-first research, at
  about 15x the tokens. Its failures included spawning far too many subagents and duplicated work from vague
  briefs.
- The Google scaling study found that centralized coordination contains errors (about 4x amplification
  against 17x for independent agents) and that multi-agent setups lose on sequential tasks.
- DOA: 0 of 9 implementation results were accepted without correction, and a verifying consolidator was
  itself wrong on its headline. Each level adds a place where errors get summarized away.

So the rules are:

1. **Claude stays the top reviewer.** A DeepSeek lead's report is a draft like any other. Claude spot-checks
   the children's reports (`runs/<child>/report.md`) behind the lead's summary, at least the claims the
   decision rests on.
2. **Give a lead a job that genuinely splits** into independent parts: a survey across many files, N
   similar records to research, or a fan-out of reviewers. Don't give it a design or integration task.
3. **Children are read-only.** Editing stays with `tools/ds_impl.ps1` worktrees that Claude launches and
   reviews.
4. **Raise `-MaxDepth` to 3 only for an experiment**, and record why in the brief.

## Reports going up

- Worker: `runs/<id>/report.md`, plus the `[ds-agent]` footer with run id and status.
- Lead: receives the children's reports as `spawn_workers` output, checks them, and writes one merged report
  citing child run ids.
- Claude: reads the lead's report, then opens child reports as needed. The manifest tree links them all.

## Seeing a lead's workers in the Background tasks panel

The Claude app's panel lists only commands the Claude session started, so a lead's workers don't appear on
their own. `launcher/ds-watch.ps1` fixes that with watcher commands Claude starts in the background:

- `-Children <lead>` exits as soon as the lead starts workers not yet watched, and prints for each one its
  `-Run` watcher command and a panel description numbered under the lead (`DeepSeek research #007.2: even
  sum (crosstalk)`).
- `-Run <run>` exits when that worker ends, printing its outcome and report, so Claude reviews each worker as
  it lands instead of waiting for the lead's merged report.

A watcher only waits; stopping one does not stop the worker.

**Evidence.** `lead-006-watch-probe.1` and `lead-007-watch-probe.1` each showed as one lead entry, one "watch
for new workers" entry and one entry per worker, and each worker entry reported its answer when that worker
finished. The first run exposed two bugs, both fixed:

- **Reused brief names break crosstalk.** A lead's worker named `research-three-backwards` had run before,
  so it ran as `.2` while its sibling was told `.1`, and the message could not be delivered. `write_brief`
  now refuses a name that already has runs.
- **A sibling that finishes can't receive.** The six-second worker exited before its sibling's message came.
  Workers told a sibling will send them something now wait for it (`wait_for_messages`, up to about 5
  minutes).

In `lead-007` both workers sent and received (`research-last-word.1`: `ammag`; `research-even-sum.1`: `72`).
