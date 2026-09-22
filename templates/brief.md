<!--
File name: <kind>-<nnn>-<slug>.md, e.g. research-083-console-camera.md.
  kind: research | websearch | impl | review | analysis | critic | advisor | digest | lead | selftest
  nnn:  next free number in the project's brief folder; check the filesystem right before writing.
The run id will be <file name>.<attempt>, e.g. research-083-console-camera.1.
The first line under "# Goal" becomes the run's title in the manifest: write it for an outsider.
-->
# Goal
<One sentence an outsider understands: the outcome, not the method.>

# Context
- Project facts and paths the worker needs; decisions already made.
- Read <project>/tasks/deepseek/context.md first (if the project has one).

# Scope
- May read: ...
- May change: ... (edit mode only; for impl briefs also the two contract lines below)
- Must not: ...

<!-- impl briefs only, read by tools/ds_impl.ps1:
Owned files: path/a.rs,path/b_test.rs
Acceptance: cargo test -p x --test b_test
-->

# Siblings
<!-- Only when launched with -Crosstalk. Name who runs beside this worker and what to tell them;
     delete this section otherwise. -->
- `research-084-radial-data.1` is mapping the radial menu's data; tell it (SendMessage) if you find the
  function that fills the ring. Shared decisions live in <contract file>; re-read it if a sibling says it changed.
- Quote in your report any message that changed what you did.

# Done when
- Concrete, checkable conditions.

# Report
- The exact shape wanted back (findings as `path:line - claim`, a table, or `templates/result-schema.json`).
- What was verified vs inferred; what is still unknown; the cheapest test that could prove it wrong.
