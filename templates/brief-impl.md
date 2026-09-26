<!--
A coder brief: impl-<nnn>-<slug>.md, run with tools/ds_impl.ps1 -Brief <this file>. Works for any project
under git: Rust, Node, Python, Go, .NET or anything with a test command.
- ds_impl makes a git worktree for the coder under local/impl/<name>, links git-ignored dependency folders
  (node_modules, .venv) into it, and lets it run the project's usual test tools plus your Acceptance commands.
- "Owned files" and "Acceptance" are read by ds_impl: one line each, comma-separated.
- The launcher adds the standard report opening (Status, Summary, Left, Next).
-->
# Goal
<What to build or fix, in one or two sentences, and why.>

# Context
- Where the relevant code is (files, functions) and how it fits together.
- Decisions already made, conventions to follow, interfaces that must not change.
- The project map is added to every brief automatically; don't repeat it.

# Scope
Owned files: <path/one.ts, path/one.test.ts>
- Change only the owned files. Everything else is reference; a file changed outside the list fails the scope check.
- No new or upgraded dependencies (package.json, Cargo.toml, pyproject.toml, lockfiles) unless the brief says so.
- No git commands: Claude reviews the diff and integrates it.

# Done when
Acceptance: <npm test | cargo test -p crate | python -m pytest tests/test_one.py | go test ./pkg/...>
- The acceptance commands pass in the worktree; run them yourself before you stop.
- A test covers the new behaviour, written to catch the change being wrong, not only to confirm it.

# Report
- What you changed and the decisions that weren't obvious.
- The commands you ran and what they printed.
- What you assumed, and the cheapest check that would show the change is wrong.
