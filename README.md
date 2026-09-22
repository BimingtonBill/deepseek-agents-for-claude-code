# DeepSeek agents for Claude Code

Claude plans and reviews while cheap DeepSeek workers research, code and check in parallel.

> An independent community project. It is not made or endorsed by Anthropic or DeepSeek.

This kit lets Claude (in Claude Code) hand work to cheap DeepSeek "workers" that run alongside it: Claude
plans and checks, the workers research, write code and review. It adds two Claude Code skills,
`deepseek-agents` and `advisor-loop`.

## What you need

- **Windows** (the scripts are PowerShell).
- **Claude Code**: the Claude desktop app (its Code tab) or the Claude Code command-line tool.
- **Python 3** on your PATH (`python --version` should work in a terminal).
- **A DeepSeek API account** with some credit: https://platform.deepseek.com. Workers are cheap, but
  they are not free, and they stop with an error when the balance runs out.

## Setup (5 minutes)

1. **Save your DeepSeek API key** so the workers can use it. Open PowerShell and paste this, then paste
   your key when it asks (it is typed hidden, and stays on your computer only):

   ```powershell
   $k = Read-Host 'DeepSeek API key' -AsSecureString; [Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY', [Net.NetworkCredential]::new('', $k).Password, 'User')
   ```

   Never paste the key into a Claude chat.

2. **Install the skills.** Download `deepseek-agents-for-claude-code.zip` from the
   [latest release](https://github.com/BimingtonBill/deepseek-agents-for-claude-code/releases/latest)
   (or use this folder if you already have it). Unzip it anywhere, then double-click `install.cmd`
   (or run `powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-skill.ps1`).
   It copies everything into `%USERPROFILE%\.claude\skills\`, backing up anything already there.

3. **Restart Claude** (close and reopen the app, or start a new `claude` session) so it sees the skills.

## Using it

In any Claude Code session, ask for it in plain words, for example:

> Use DeepSeek workers to find every place this project reads the config file, and summarise them.

or type `/deepseek-agents`. Claude writes a brief, starts the workers in the background, keeps working
itself, and checks what they send back. Running workers show up in the app's Background tasks panel as
`DeepSeek <kind> #<number>: <what it does>`.

**How much Claude hands off** is a dial from 0 (never) to 10 (everything). The default is 5. To change it
for one project, open a terminal in that project's folder and run:

```powershell
python "$HOME\.claude\skills\deepseek-agents\tools\ds_delegation.py" --set 7 --agents-md
```

`--agents-md` writes the rule into the project's AGENTS.md so every Claude session there sees it.
Use `--global` instead of `--agents-md` to set your default for all projects. `--table` shows every level.

## Good to know

- **Workers can't see your Claude login or history.** They run with only your DeepSeek key, and only
  read the project folder you point them at.
- **Workers are cheaper than Claude but less reliable.** Claude reviews everything they do before using
  it; keep it that way.
- **Missing tools:** if a job needs something you don't have installed (a compiler, a Python package),
  Claude is told to stop and ask you to install it rather than work around it.
- **Stopping a runaway worker:** `powershell -File "$HOME\.claude\skills\deepseek-agents\tools\ds_status.ps1"`
  from the project folder lists running workers; add `-Stop <name>` to stop one.

## If something goes wrong

| Message | What to do |
|---|---|
| `DEEPSEEK_API_KEY is not set` | Do setup step 1 again. |
| `DeepSeek rejected DEEPSEEK_API_KEY (401)` | The key is wrong; create a new one on platform.deepseek.com and redo step 1. |
| `balance is too low` / `402` | Add credit to your DeepSeek account. |
| `Claude Code was not found` | Install the Claude desktop app or Claude Code, or set `DEEPSEEK_AGENT_CLAUDE` to the full path of `claude.exe`. |
| `crosstalk is off for this run: it needs Python` | Install Python 3 and make sure `python` works in a terminal. |

The `docs/` folder explains how it all works, if you're curious.

## License

MIT. See `LICENSE`.
