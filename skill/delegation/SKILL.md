---
name: delegation
description: Show or set the DeepSeek delegation level (1-5), how much Claude hands to DeepSeek workers in this project or by default.
argument-hint: "[1-5] [global]  |  table"
disable-model-invocation: true
---

# /delegation

The user typed `/delegation $ARGUMENTS`. Run the matching command below with the Bash tool from the project folder, then answer in two or three plain sentences: the level, where it is set, and what it means in practice. Don't paste the whole output back.

The tool is `python "$HOME/.claude/skills/deepseek-agents/tools/ds_delegation.py"` (add `--project "<project folder>"` when the session's folder isn't the project).

| The user typed | Run |
|---|---|
| nothing | the tool with no options: the level here, where it comes from, what it means |
| a number 1-5 | `--set <n> --agents-md`: sets it for this project and writes its rules into the project's AGENTS.md, where every session sees them |
| a number and `global` (or "default", "everywhere") | `--set <n> --global`: the default for projects that don't set their own |
| `table` (or "levels", "list") | `--table`: all five levels |

After setting a project level:
- If the project's AGENTS.md or CLAUDE.md also describes a delegation level in its own words (outside the block between the `ds-delegation` markers), update those words too, so the two don't disagree. Show the user what you changed.
- Say that sessions already open pick up the change on their next session start. A running session can re-read AGENTS.md to pick it up now.

Anything else in the arguments (a level outside 1-5, words you can't map): show the current level and the table, and say what the command accepts.
