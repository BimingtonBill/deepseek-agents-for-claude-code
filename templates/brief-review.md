<!--
A review brief: review-<nnn>-<slug>.md. For a coder's work, ds_impl.ps1 prints a ready review command after a
PASS (run it in the coder's worktree: it can see the diff and re-run the acceptance commands). Use this
template for anything else worth a second pair of eyes: a design note, a report, a finished change.
The launcher adds the standard report opening (Status, Verdict: accept | fix first | reject, Summary, Left, Next).
-->
# Goal
<What is being reviewed and the question the review answers, e.g. "Is impl-183's field-notes capture safe to merge?">

# Context
- What the work was meant to do (its brief, the decision it implements), and where it is.
- What was already checked (acceptance results, earlier reviews), so the review looks elsewhere.

# Scope
- Read only. Run: <the read-only commands it may use, e.g. `git diff`, the tests>.
- Do not fix anything: report.

# Done when
- Every claim the work makes has been checked or marked as not checked.
- The verdict is one of accept, fix first, reject.

# Report
- Findings as `path:line - problem - why it matters`, most serious first.
- What you ran and what it printed; what you only read.
