<!--
A brief for a DeepSeek lead: launch with -CanSpawn. File name lead-<nnn>-<slug>.md.
Give a lead only a job that splits into independent parts (see docs/design/hierarchy.md).
-->
# Goal
<The whole job, in one sentence an outsider understands.>

# Context
- What the parts are and why they are independent.
- Shared facts every worker needs (the lead must copy them into each worker's brief: workers see only their brief).

# How to split it
- Suggested parts: <part 1>, <part 2>, ... (at most 6 workers).
- Kinds to use: research for fact-finding, review to check another worker's notes, analysis for run output.
- Crosstalk: <on/off>. If on, name in each worker's brief which siblings it should tell what.

# Scope
- The lead and its workers are read-only. Nobody edits files.
- Do small things yourself; spawn only for genuinely independent parts.

# Done when
- Every part has a worker report, and you have checked the claims your summary rests on.

# Report
- One merged answer.
- Per worker: run id, one-line result, what you checked and whether it held.
- Disagreements between workers and how you settled them (or that you could not).
- What is still unknown.
