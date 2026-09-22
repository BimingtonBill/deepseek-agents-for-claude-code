---
name: deepseek-agents
description: Lead a team of DeepSeek V4.1 worker agents. You plan, delegate and review; headless DeepSeek-powered Claude Code workers do well-scoped subtasks (exploring code, mechanical edits, tests, drafts). Use when the user asks for DeepSeek agents or workers, asks you to lead or delegate to DeepSeek, or runs /deepseek-agents, and whenever the project's AGENTS.md sets a DeepSeek delegation level of 2 or more.
---

# DeepSeek worker agents

You are the lead. Each worker is a separate headless Claude Code process running on DeepSeek V4.1 Flash (`deepseek-flash`) through DeepSeek's Anthropic-compatible API, started by `ds-agent.ps1` in this skill's folder. A worker sees only the brief you write (not this conversation, not the user's Claude login) and returns one final report. Workers are cheaper than you but less reliable: you own the plan, the integration and the final quality.

Claude Code's built-in Agent tool can't do this, because its subagents always use your provider. For DeepSeek work, use this script, not the Agent tool.

## When to delegate

Good worker tasks are self-contained and checkable: map or summarize part of a codebase, find every usage of something, apply a mechanical change across files, write tests against a clear spec, draft docs or boilerplate.

**Workers can see images.** DeepSeek V4.1 is multimodal and Claude Code's `Read` hands it the picture, so a brief can point at a screenshot, a mockup or a diagram and ask what is in it, or ask for two images to be compared. Say the path in the brief; the worker reads it like any other file.

Keep for yourself: design and architecture decisions, ambiguous requirements, security-sensitive code, anything that needs this conversation's context, and anything quicker to do than to brief.

## 0. Check the tools before planning

Before you plan or delegate, check that the tools the job needs are installed: compilers, runtimes, package managers and libraries. Use this skill's checker, not `which`:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME/.claude/skills/deepseek-agents/ds-which.ps1" g++ cmake cargo rustc clang++ py:numpy py:PIL
```

It prints one line per tool (found with path and version, or MISSING, with the pip command for Python packages). It checks against the PATH as saved in Windows *now*. Your session inherited the PATH from when the Claude app started, so anything installed since (Rust via rustup on 2026-09-21, for example) is invisible to `which` and would be wrongly reported missing. Workers get the refreshed PATH from the launcher automatically.

**If something the best approach needs is missing, stop and ask the user to install it.** Don't start the work, pick a weaker approach, or have workers hand-write a substitute (a homemade image writer instead of Pillow, pure Python instead of numpy). Tell the user:
- what is missing and what it is for;
- the exact install command (`winget install ...`, `pip install ...`, `conda install ...`);
- what you'd do instead if they'd rather not install it, and what that costs.

Don't install it yourself unless the user says to. Go ahead without the tool only when the user chooses to. Workers follow the same rule: they report a missing tool to you instead of working around it (the launcher tells them so), and you bring it to the user.

## 1. Write the brief

Write each brief to its own UTF-8 file in your scratchpad directory (or `$env:TEMP`). Make it complete, because the worker cannot ask questions:

```
# Goal
The outcome you want, in one or two sentences.
# Context
Relevant files and paths, conventions, decisions already made.
# Scope
Which files it may change (edit mode) and what is off-limits.
# Done when
Concrete checks the work must pass.
# Report
The exact shape of the answer you want back, e.g. findings as path:line - issue.
```

If the brief tells the worker to run commands (in backticks, e.g. `` `cargo test -p gpu` ``), give it matching `-AllowTools` rules. The launcher warns (`the brief names commands this worker may not run`) when a backticked command has no matching rule, or uses inline `python -c`, which workers can never run. Fix the rules or the brief before going on: a worker told to run something it can't will spend its turns working around it.

## 2. Run the worker

```
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME/.claude/skills/deepseek-agents/ds-agent.ps1" -TaskFile "<brief file>" -Dir "<project folder>" -Mode read
```

The same command works from both the Bash and PowerShell tools.

| Option | Effect |
|---|---|
| `-Mode read` (default) | Read, Grep and Glob only |
| `-Mode edit` | Adds Edit and Write, auto-approved inside `-Dir` only |
| `-AllowTools "Bash(npm test *),Bash(git diff *)"` | Extra permission rules, comma-separated in one string; their tools are enabled too. Anything else that needs approval is denied. |
| `-AddDir "D:/ref/other-project"` | Extra folders the worker may read but never change. Use this for reference material outside the project. |
| `-DenyEdit "src/**,README.md"` | Paths inside the project that no file tool and no shell redirect may change. |
| `-Label <name>` | Names the run in `runs.csv` and in the state file. Defaults to the brief's file name. |
| `-Bare` | Faster start, no project instructions — but the worker then has `Read` only, with no Grep and no Glob. Only worth it for a one-file task. |
| `-Schema <file.json>` | A JSON Schema the final report must satisfy, when you want a result you can parse instead of prose. Works with DeepSeek. |
| `-WebDomains "docs.example.com"` | Lets the worker fetch those domains. Off by default: a web page is untrusted text, so keep it away from workers that can edit and commit. |
| `-Resume <session id>` | Continue a worker's conversation (the id is in its footer). Use the same `-Dir`, and give the follow-up with `-Task "..."` or `-TaskFile`. The run keeps its run id and messaging name, so crosstalk partners can still reach it; its report gets a `## Resume <n>` section, and the manifest counts `resumes`. |
| `-Task "<text>"` | Inline brief, for short follow-ups |
| `-Extra "<text>"` | Appended to the brief under a "This run" heading, so a standing role brief (reviewer, analyst, critic) can be pointed at today's target: `-Extra "Task: impl-006. Checkout: <path>."` |
| `-Model <id>` | DeepSeek model. Default `deepseek-flash[1m]` (V4.1 Flash with its 1M context). |
| `-Effort low\|high\|max` | How long the worker thinks before each step; default `max`. See "Effort" below. |
| `-MaxTurns 60`, `-TimeoutMinutes 30` | Limits |
| `-Kind research` | What sort of run this is (research, impl, review, analysis, critic, advisor, digest, lead, selftest, probe). Inferred from the label's prefix, including the old `t##`/`i##`/`c##` names. |
| `-Title "..."` | One line saying what the run is for. Defaults to the first line under the brief's `# Goal`. |
| `-NoCrosstalk` | Turn off crosstalk, which is **on by default**: workers can message other live workers (ListAgents, SendMessage, a wait tool). `"crosstalk": false` in `.deepseek-agents.json` turns it off for a project, and `-Crosstalk` forces it on over that. See "Crosstalk" below. |
| `-CanSpawn` | Makes the worker a DeepSeek lead that can launch its own read-only workers. See "Hierarchy" below. |
| `-SubAgents` | Gives the worker Claude Code's Agent tool; its subagents also run on DeepSeek Flash. |
| `-MaxDepth 2` | Deepest level any spawned worker may sit at; Claude's own workers are depth 1. |
| `-DryRun` | Print the command, policy, run id, lineage and environment without running |

Output is the worker's report, then a footer: `[ds-agent] run=<run id> session=<id> status=ok turns=<n> tokens_in=... tokens_out=...`. On failure, status reads `error(<reason>)`, e.g. `error(error_max_turns)`, and the report text holds the error message. A `[claude-code:unrecognized_model]` line on stderr is expected, because Claude Code doesn't know DeepSeek's model names. A `denied=` entry means the worker tried a tool it was not allowed. Decide whether to rerun it with more `-AllowTools` rules or do that step yourself.

Workers often take several minutes. Run each one as a background command (`run_in_background: true`); its completion notification will interrupt whatever you are doing then. A worker's run time is your work time, not a wait: see "Work while workers run".

**Name the background command for the user.** The app's Background tasks panel shows only the command's description, so write it in this fixed format: `DeepSeek <kind> #<nnn>: <what it does>`, e.g. `DeepSeek impl #002: core scene + path tracer` or `DeepSeek review #007: check impl-004's BVH`. Add `(retry 2)` for a second attempt, `(resume 1)` for a resume, `(lead, spawns workers)` for `-CanSpawn`, and `(crosstalk)` when the brief has the worker talk to named siblings. Keep the whole description under about 60 characters so the panel doesn't cut it off.

When you redirect a worker's output to a file, do not name it `<stateDir>/<label>.json`: that is the launcher's own state file and it is deleted when the run ends, taking your output with it. Use another name or another folder.

While a worker runs, `<stateDir>/<label>.json` holds its `claude.exe` pid and the `taskkill` line that stops it — the worker survives its launcher being killed, so that file is how you stop a runaway. Each finished run appends a row to `<stateDir>/runs.csv` (status, turns, tokens, seconds, denied tools). `stateDir` is `local/agents` when the project has a `local/` folder, otherwise `~/.claude-deepseek/agents`.

## Effort

DeepSeek has three thinking levels. Pick one per worker:

| `-Effort` | Use for | Cost |
|---|---|---|
| `low` | Mechanical work with an obvious method: renames, formatting, copying a pattern across files, simple lookups | Cheapest and fastest; gives up early on anything hard |
| `high` | Ordinary research, reviews and bounded code with a clear spec | Middle |
| `max` (default) | Hard reasoning: debugging, algorithms, maths, reverse engineering, anything where a wrong answer is expensive | Can think for 100k+ tokens on one step |

Measured on 2026-09-21 on a hard counting problem: `low` stopped after 24k tokens with a wrong answer, and `max` thought for 107k tokens and got it right. Workers get a 128k output cap per step (the launcher sets it; Claude Code's own default of 32k would cut a `max` answer off with nothing returned). When unsure, use `max`: DeepSeek is cheap and a wrong answer costs your review time. **For anything numeric or algorithmic, let the worker compute instead of reasoning it all out.** Allow it to write and run a script (`-Mode edit -AllowTools "Bash(python *)"`; inline `python -c` is always denied). Given only reasoning, a `max` worker on a hard counting problem spent two full 128k steps thinking and never answered. Allowed a script, it got the right answer in 12 turns and checked it three ways. `medium` and `xhigh` are still accepted for old commands, but DeepSeek runs them as `high` and `max`, and the manifest records what actually ran.

## Names and the manifest

Name briefs `<kind>-<nnn>-<slug>.md` (e.g. `research-083-console-camera.md`), with the number taken from the filesystem right before writing. The run id is `<brief name>.<attempt>`: `.1` first, and a fresh rerun of the same brief is `.2`, `.3`... A `-Resume` is not a new attempt: it keeps the run id. Never invent `t81b`-style names. The run id is also the worker's messaging name.

Each run keeps `<stateDir>/runs/<run id>/` with `brief.md`, `report.md` and `manifest.json` (kind, title, parent, lineage, state, turns, tokens including in-process subagents), and `<stateDir>/manifest.jsonl` gets `submit`, `start` and `end` lines per run (again for each resume). Failed, timed-out and cancelled runs are recorded too. The report holds every turn's final text: if a sibling's message arrives after the worker's report, the extra turn is appended under a separator instead of replacing the report. To see them:

```
python "$HOME/.claude/skills/deepseek-agents/tools/ds_manifest.py" --tree        # from the project folder: Claude -> leads -> workers
python "$HOME/.claude/skills/deepseek-agents/tools/ds_manifest.py" --write       # writes <stateDir>/MANIFEST.md
```

## Crosstalk

Crosstalk is **on by default**: workers that run at the same time can message each other by run id (Claude Code's own cross-session messaging, with inbound messages set to accept). A message lands between the receiver's tool calls, and a `wait_for_messages` tool lets a worker pause for one. Workers are told to message only the siblings their brief names (and workers started by the same lead), since `ListAgents` shows every live worker on the machine, other projects' included. Claude cannot see or message workers: they live in a separate config folder so they never see your login.

For crosstalk to be useful, the brief has to set it up:
- name each sibling by run id, and say what to tell it (a finding, a changed interface, a file about to change), not just that it may talk;
- start siblings that must talk at the same time, because a finished worker can't receive;
- if a worker must receive something, say so: it then waits for the message before finishing;
- **match run lengths, or route late results through a file.** A message to a worker that has already finished is lost, and `SendMessage` still says `success` (stress test 2: 3 of 6 "ok" sends were never read). A `max` worker told to notify two `high` siblings when its fix lands can never reach them (54 min against 29 and 34; the siblings burned five-minute waits). So: give siblings that must exchange results the same effort and similar work, and for a result that lands late, name a file in both briefs (the sender writes it, the receiver reads it if the message never came). Workers are told to check `ListAgents` before an important send and to put undeliverable results in their report;
- keep shared decisions in a contract file that the messages point to;
- have every report quote any message that changed what the worker did.

Turn it off (`-NoCrosstalk`) for a worker that must not be interrupted or whose work touches nothing else running.

## Hierarchy

A worker launched with `-CanSpawn` is a DeepSeek lead. It gets `write_brief` and `spawn_workers` tools, runs up to 6 read-only workers in parallel in its folder (with crosstalk unless it turns it off), checks their reports, and returns one merged report that cites their run ids. Lineage and the depth limit are enforced by the launcher. Use a lead only for a job that splits into independent parts, and start from `templates/brief-lead.md`. **You still review:** open the child reports behind any claim you act on. For quick fan-out inside one worker, `-SubAgents` gives it the Agent tool, but its subagents get no manifest record of their own.

**Show a lead's workers in the Background tasks panel.** The panel lists only commands you started, so give each of the lead's workers a watcher there. `ds-watch.ps1` is in this skill's folder; run every command below from the project folder, in the background:

1. Start the lead as usual, described `DeepSeek lead #<nnn>: <what> (lead, spawns workers)`.
2. Start `ds-watch.ps1 -Children <lead task id>`, described `Watch lead #<nnn> for new workers`. It exits as soon as the lead starts workers you aren't watching yet, and prints for each one the exact `ds-watch.ps1 -Run <run id>` command and its panel description (`DeepSeek research #<nnn>.<k>: <what>`, numbered under the lead).
3. When it exits, start each printed `-Run` watcher with its printed description. If the lead is still running, start the printed `-Children ... -Known ...` command again, so later workers get entries too.
4. Each `-Run` watcher exits when its worker ends, and prints the outcome and report. Review each report as it lands; don't wait for the lead's merged report.

**Don't block while a lead runs.** Its watchers only help if you're free when they fire: a long foreground wait (a `sleep` loop, a command that polls for minutes) holds you there, and a lead's new workers get no panel entry until it ends. Wait for notifications instead.

A watcher only waits: stopping one in the panel does not stop the worker (`tools/ds_status.ps1 -Stop <label>` does). If the manifest isn't in `<project>/local/agents`, pass `-StateDir`.

## Delegation level: how much to hand off

Each project has a delegation level from 1 to 5 that says how much of the work goes to workers. Check it before deciding whether to delegate: from the project folder, run `python "$HOME/.claude/skills/deepseek-agents/tools/ds_delegation.py" --brief`. It prints the level and its rule. The level comes from, first match wins: the `DS_DELEGATION_LEVEL` environment variable, `"delegationLevel"` in the project's `.deepseek-agents.json`, `~/.claude-deepseek/config.json`, else 3. An old 0-10 `"delegation"` value still works and is mapped (7 reads as 4). When the project's AGENTS.md has a generated "DeepSeek delegation level" block, that block is the same rule.

| Level | Rule |
|---|---|
| 1 | Only when asked. Claude does the work itself unless the user asks for a worker. |
| 2 | Research and review: delegate non-trivial research, big read-only surveys, reviews and run analyses. Claude writes all code. |
| 3 | Default. As 2, plus bounded self-contained implementation through `ds_impl.ps1` and anything that can be briefed with a clear check; parallel, with reviewers. |
| 4 | Claude manages: plans, briefs, reviews and integrates; workers explore and do most coding. Claude doesn't read source beyond what review needs; several workers busy, leads where they fit. |
| 5 | Everything: Claude only orchestrates; every task, even small edits and lookups, goes to a worker unless it needs this conversation, a GUI or the user. |

At **every** level Claude keeps the conversation with the user, design decisions, integration, security-sensitive changes, and review of every worker result it acts on. The dial moves work, not the quality bar. When the user says "use workers more" or "less", or names a number, set it with `ds_delegation.py --set <1-5> --agents-md` from the project folder (`--global` sets their default for all projects) and say what changed.

## Project policy: .deepseek-agents.json

A project can keep its worker policy in `.deepseek-agents.json` at its root, so every launch gets it without repeating flags:

```json
{
  "readOnlyDirs": ["D:/Games/Example"],
  "denyEdit": ["src/**", "AGENTS.md"],
  "denyRead": ["secrets/**"],
  "deny": ["Bash(rm *)"],
  "allowTools": "Bash(git add *),Bash(git commit *)",
  "_note": "allowTools applies to edit-mode runs only; read mode stays Read/Grep/Glob",
  "stateDir": "local/agents",
  "delegationLevel": 3,
  "defaults": { "mode": "edit", "effort": "max", "maxTurns": 400, "timeoutMinutes": 150 }
}
```

Explicit flags always beat `defaults`. Deny rules cover the file tools and the shell redirects Claude Code recognises, but not a script the worker writes and runs, so keep stating the rule in the brief as well. When a project has one, read it before writing briefs: it tells you what workers may touch. `-DryRun` prints the resolved policy.

## 3. Run several in parallel

Start independent workers in one message, each as its own background command. Give edit-mode workers disjoint files: two workers must never edit the same file. For large or risky edits, give each worker its own git worktree as `-Dir` and merge the results yourself.

**Parallel workers must not share build output.** Disjoint source files are not enough: in a Rust workspace every checkout gives a crate's test binary the same name, so two workers sharing one `target/` overwrote and ran each other's tests (OpenSkyrim impl-006/impl-007: an "acceptance FAIL" that was really the neighbour's binary). The harness's `tools/ds_impl.ps1` gives each task its own `target/` inside its worktree, and seeds it with a copy of the lead's `target/debug`, which takes seconds (6.6 GB in 6 s), so only the workspace's own crates rebuild (17 s instead of a cold Bevy build). `-NoSeed` starts it empty. If you launch parallel edit workers any other way, set `CARGO_TARGET_DIR` per worker yourself. The same applies to any build tool with one shared output folder.

The harness's tools (`ds_impl.ps1`, `ds_status.ps1`, `run_ds_queue.ps1`, `ds_report.py`, `ds_manifest.py`, `ds_delegation.py`, `check_*.py` ...) are installed in this skill's `tools/` folder (`$HOME/.claude/skills/deepseek-agents/tools/`). Run them from the project folder and they act on that project: `powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME/.claude/skills/deepseek-agents/tools/ds_impl.ps1" -Brief <brief>`. A project can also copy them into its own `tools/` unchanged: a copy acts on the project it sits in and launches workers through this skill. Diff first if the project has customised its copy.

An acceptance failure from a parallel run is not evidence until you know the build was the worker's own. Record the real cause in `pilot.csv` when you accept over a harness verdict. `python tools/ds_report.py` sums the record, and now counts denied tools by name (`5 with denied tools (Bash 5, Glob 1)`).

## Work while workers run

Workers run for minutes; a launch that leaves you idle until the report arrives wastes most of that time. In the OpenSkyrim Blackreach demo, Claude launched three workers, did two minutes of its own work, then announced "all three workers are running" and did nothing for the remaining 3.5 minutes; later it sat through a 10-minute release build with no worker running at all. The right shape is: Claude and the workers busy at the same time, on things that cannot collide.

**Before launching, decide what you will do while they run.** When you plan a batch, split the job into the workers' parts and Claude's own part, and say both in the same message. Claude's part is work that needs this conversation or your judgement and touches nothing a worker owns:
- the next brief(s), drafted from what is already known so they are ready to launch the moment a worker's report lands (a report that changes the brief is a small edit, not a restart);
- integration plumbing for the results that are coming: the wiring, config flags, module registration and test fixtures the worker's files will plug into, in files no worker owns;
- reviewing the *previous* worker's report and diff, and spot-checking its claims;
- your own tests, builds, screenshots and measurements of already-integrated work;
- writing the design or contract for the phase after this one;
- housekeeping: handoff notes, the queue file, the manifest, commits of finished work.

**Keep read-only workers out of your scratch.** A research worker with the whole project readable will read `local/impl/*` worktrees and live logs and mix them up with the real tree (stress test 2: one attributed numbers to the wrong build from file times). Put `local/**` in the project's `denyRead`, or add `-DenyEdit`-style read limits for the run, and name the exact files it should read in the brief.

**What not to do in parallel:** anything in a file a running worker owns; a build in a shared output folder a worker is building into (see the target/ rule above); an acceptance run of a worktree still being written. Running the game, the GPU or a physical device stays serial.

**Long commands of your own are background tasks too.** A release build, a data conversion or a test campaign that takes minutes is the same case as a worker: start it in the background, do the next thing, and let its notification bring you back. Chain the two: when the build finishes, the next worker can be briefed against it.

**When a report lands, finish your current step before switching.** The notification interrupts you; note it, complete the edit or command in hand, then review. Don't leave your own work half-done to read a report that will wait.

**Keep enough independent work queued.** A batch of three workers plus one Claude-side task is well balanced; a batch of three workers plus "watch them" is not. If you cannot think of anything safe to do while they run, that is a sign the split is wrong: either the workers have the whole job and you should give one of them the reviewer's role too, or you kept something that should have been a fourth brief.

## 4. Review before you accept

Treat every report as a draft from a junior engineer:

- Spot-check its claims by opening the cited files and lines.
- After an edit-mode run, read the full `git diff` of what the worker changed and run the tests or build.
- After integrating a worker's files, a suspiciously fast build means stale sources: the build tool thinks nothing changed. `ds_impl.ps1 -Integrate` refreshes the copied files' timestamps for this reason; if you copy files another way, touch them first.
- If the work is off, resume the same worker with specific corrections, or fix it yourself when that is faster.

Tell the user which parts DeepSeek workers did.

## Setup and errors

- `DEEPSEEK_API_KEY is not set`: ask the user to run this in their own PowerShell window. Never ask them to paste the key into the chat.
  `$k = Read-Host 'DeepSeek API key' -AsSecureString; [Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY', [Net.NetworkCredential]::new('', $k).Password, 'User')`
  The script reads the saved variable directly, so nothing needs restarting.
- `Claude Code was not found`: the user needs the Claude Code CLI or the Claude desktop app installed, or `DEEPSEEK_AGENT_CLAUDE` set to the full path of `claude.exe`.
- An authentication error (401) comes from DeepSeek and means the key is wrong. A 402 means the DeepSeek account has run out of balance.
