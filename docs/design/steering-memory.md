# Nudges, project memory and the morning report

Built 2026-09-24 from the OpenSkyrim night of 2026-09-23: the 20 runs of 100+ steps made up 85% of
the night's spend; coders slept 73 minutes waiting on background builds; "cd" was refused 103 times; two
runs lost their reports; and every worker explored the project from scratch.

## Nudges (`launcher/ds_steer.py`)

The launcher's 15-second loop calls `watch`, which reads this launch's part of the transcript and queues
a message in `runs/<id>/nudge.txt` the first time a sign of drift appears (100/150/200 steps with tools,
200k/350k context, one command form refused 3 times, a sleep of 2 minutes or more). Each worker's
settings carry a PostToolUse hook that runs `deliver`: it hands the queued text to the worker as
`additionalContext` and deletes it. `steer.json` keeps every nudge for the morning report.

Evidence:
- `probe-037-nudge` proved nothing: a probe worker in this repo has no Bash, so the refusals it was told
  to cause never happened. It reported that plainly.
- `probe-038-nudge-delivery`: a message written into the run's `nudge.txt` 4 s after launch reached the
  worker after its next tool call, word for word, once ("Note from the launcher: PROBE-038 test
  nudge ...", "arrived after part 2 ... as a PostToolUse hook additionalContext block").
- Detection on real transcripts: impl-103 (280 steps, $2.45) and research-542 (235 steps, crashed) would
  have been nudged at 100, 150 and 200 steps and at 200k/350k context; impl-525 at its 540-second sleep;
  impl-537 after its fifth refused `cd`.

Whether nudged workers stop sooner is not proven yet: the next nights' morning reports will show.

## Brief size check (`tools/ds_impl.ps1`)

Over 38 OpenSkyrim coders, owned-file size predicted length; file count and brief length hardly did:
under 4,000 owned lines, a median of about 95 steps; 4,000-8,000, 124 (69% over 100); over 8,000, 186
(94% over 100). `ds_impl.ps1` prints a size note above 4,000 lines, before any money is spent. Caveat:
the lines were counted at today's HEAD, not at each run's base, and OpenSkyrim's largest files have
since been split, so the bands are approximate.

## Project memory (`tools/ds_memory.py`)

`<state dir>/memory/map.md` and `pitfalls.md`, written by digest workers from briefs the tool builds
(the map brief includes a free skeleton: folders, largest files, workspace members, doc headings; an
update carries the old map and the commits since). The launcher appends them to the brief (stdin, not
the command line, which Windows caps at 32,767 characters): the map for every kind except websearch,
probe and selftest; pitfalls for impl, lead, review, critic and task. Not on a resume.

Evidence (this repo): `digest-map.1` wrote a 1,165-word map in 97 s for $0.04; `digest-pitfalls.1`
turned 8 review reports into 10 rules, each citing its run, in 83 s for $0.02 (including the planted
HEAD_START change from `review-035`). `research-041-map-with` confirmed it received the map.
`research-041` (with) and `research-042` (without) on the same lookup: 5 steps/$0.007 against 6
steps/$0.006, so the question was too easy to show a saving. The saving has to show on real coder-size
tasks, in the morning reports' step counts.

## Morning report (`tools/ds_morning.py`)

Local only; 2.7 s for OpenSkyrim's 42 runs of a night. `ds_hook.py` runs its short form at SessionStart
(startup, resume) and hands it to Claude as context when workers ran since the last report, saving the
full report under `<state dir>/reports/`. Simulated session starts: the first printed the summary and the
report path; a second, with nothing new, printed nothing; a folder without `local/` printed nothing.
