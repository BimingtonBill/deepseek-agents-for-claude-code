# DeepSeek agents for Claude Code

**Give Claude a team of cheap helpers.** Claude stays in charge and does the thinking that matters, while
DeepSeek AI "workers" do the legwork in the background: reading through code, researching, writing
first drafts of code, and checking each other's work.

> An independent community project. It is not made or endorsed by Anthropic or DeepSeek.

## What is this, in plain words?

[Claude Code](https://claude.com/claude-code) is Claude working directly on the files on your computer.
It's great, but big jobs eat into your Claude usage limits, and Claude does one thing at a time.

This add-on lets Claude act like a **manager**:

- You ask Claude for something, as usual.
- Claude breaks the job into pieces and hands some of them to **DeepSeek workers**: separate, much
  cheaper AI helpers that run on your computer in the background.
- While they work, Claude keeps working on its own part.
- When a worker finishes, Claude **checks its work** before using it. Nothing a worker does goes in
  without Claude looking at it.

You'll see the workers in Claude's **Background tasks** panel, with names like
`DeepSeek research #004: find where the game loads save files`.

## What does it cost?

- **DeepSeek charges per use, and it's cheap.** A typical worker task costs a few cents, and big ones
  up to about 20 cents. Topping up $5 goes a long way.
- **It saves your Claude usage.** The heavy reading and drafting happens on DeepSeek, so your Claude
  plan lasts longer.
- You still need your normal Claude plan that includes Claude Code.

## What you need

- A **Windows** computer.
- The **Claude desktop app** ([download](https://claude.ai/download)) with a plan that includes Claude
  Code, or the Claude Code command-line tool.
- A **DeepSeek account** with a little credit. Sign up at [platform.deepseek.com](https://platform.deepseek.com),
  add credit under **Top up**, and create a key under **API keys**. Keep that key handy: you'll paste it
  once during setup.
- **Python 3.** If you don't have it, setup tells you how to get it.

## Install it: the easy way

Open the Claude desktop app, go to the **Code** tab, start a session, and paste this in:

```text
Please install "DeepSeek agents for Claude Code" for me.

1. Download https://github.com/BimingtonBill/deepseek-agents-for-claude-code/releases/latest/download/deepseek-agents-for-claude-code.zip into a new folder called "deepseek-agents-setup" in my Downloads folder, and unzip it there.
2. Read setup.ps1 in the unzipped folder so you know what it does, then run it:
   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
   It installs the skills and checks for Python and Claude Code. If I haven't saved a DeepSeek API key yet, it opens a separate window where I type the key myself.
3. Tell me in plain words what it reported and what I need to do next.

Never ask me to type or paste my DeepSeek API key into this chat.
```

Claude will ask your permission before it downloads and runs things; say yes. If a window pops up
asking for your **DeepSeek API key**, paste the key there (nothing shows as you paste; that's normal)
and press Enter. It checks the key with DeepSeek and shows your balance.

When it's done, **close and reopen the Claude app.**

> **Why a separate window for the key?** Your key is like a password for your DeepSeek account. Anything
> typed into a Claude chat is saved in the chat. The separate window keeps the key out of it, and stores
> it privately on your computer.

## Install it: by hand

1. Download `deepseek-agents-for-claude-code.zip` from the
   [latest release](https://github.com/BimingtonBill/deepseek-agents-for-claude-code/releases/latest) and unzip it.
2. Double-click **`install.cmd`** in the unzipped folder. It installs everything and, if needed, opens the
   window for your DeepSeek key.
3. Close and reopen the Claude app.

## Using it

Just ask Claude in plain words, in any project:

- *"Use DeepSeek workers to find every place this project reads its settings file, and summarise them."*
- *"Have DeepSeek research how other mods handle save files while you work on the menu."*
- *"Get a DeepSeek worker to review the change you just made."*

Or type `/deepseek-agents` to switch it on for the session.

## How much should Claude hand off? The delegation dial

A setting from **0 to 10** tells Claude how much work to give DeepSeek. Higher means Claude hands off more
and uses less of your Claude limits, but more of the work is first done by DeepSeek, which is cheaper and
less reliable, so Claude spends its time checking instead.

| Level | Name | What Claude does |
|:---:|---|---|
| **0** | Off | Does everything itself and never uses DeepSeek. |
| **1** | Only when asked | Uses DeepSeek only when you ask it to. |
| **2** | Suggests | May *suggest* DeepSeek for big reading jobs, but asks you first. |
| **3** | Big reading jobs | Hands off large reading and searching (many files, long logs). Writes all code itself. |
| **4** | Research and checking | Hands off research, reviews and test-result analysis. Writes all code itself. |
| **5** | **Balanced (the default)** | As 4, and also hands off small, self-contained pieces of code (a new tool, a test file). |
| **6** | DeepSeek first | Anything that can be clearly described goes to DeepSeek, several jobs at once, with a DeepSeek reviewer on code. |
| **7** | **Claude manages** | Claude plans, writes the instructions, checks and fits the pieces together. DeepSeek does most of the exploring and coding. *A good choice for bigger projects.* |
| **8** | Heavy | As 7, and Claude avoids reading code itself beyond what checking needs. |
| **9** | Nearly everything | As 8, and even small edits and lookups go to DeepSeek. |
| **10** | Everything | Claude only manages: every task goes to DeepSeek unless it needs you or this conversation. |

**What never changes, at any level:** Claude talks to you, makes the design decisions, puts the pieces
together, handles anything security-sensitive, and **checks every piece of DeepSeek work before using it**.

**How to change it:** just tell Claude, for example:

- *"Set the DeepSeek delegation level to 7 for this project."*
- *"Make DeepSeek delegation 3 my default for all projects."*

## Is it safe?

- **Workers only see the project you point them at.** They can't see your Claude account, your chats or
  other folders.
- **Your DeepSeek key stays on your computer**, saved for your Windows account only.
- **Workers can't change files they weren't given.** Coding tasks happen in a separate copy of your
  project, and Claude reviews the changes before bringing them in.
- **If a job needs a program you don't have**, Claude stops and asks you to install it rather than
  working around it.

## If something goes wrong

| You see | What to do |
|---|---|
| `DEEPSEEK_API_KEY is not set` | Run `install.cmd` from the unzipped folder again; it reopens the key window. |
| `DeepSeek rejected DEEPSEEK_API_KEY (401)` | The key is wrong or was deleted. Create a new one at platform.deepseek.com and run `install.cmd` again. |
| `balance is too low` / `402` | Add credit at [platform.deepseek.com/top_up](https://platform.deepseek.com/top_up). |
| `Claude Code was not found` | Install the Claude desktop app and open its Code tab once. |
| `it needs Python` | Install Python: `winget install Python.Python.3.12`, then restart Claude. |
| A worker seems stuck | Ask Claude: *"Show me the running DeepSeek workers and stop the stuck one."* |

## For the technically curious

- `skill/`: the two Claude Code skills (`deepseek-agents`, `advisor-loop`) that teach Claude how to lead workers.
- `launcher/`: `ds-agent.ps1` starts one worker as a headless Claude Code process pointed at DeepSeek's
  Anthropic-compatible API, with its own permissions, a 128k output cap and a run record.
- `tools/`: coding tasks in isolated git worktrees (`ds_impl.ps1`), run status, the run manifest, the
  delegation dial, result and citation checkers.
- `docs/design/`: how naming, crosstalk between workers, DeepSeek leads, effort levels and the
  delegation dial work, with the test evidence behind each.

## License

MIT. See [`LICENSE`](LICENSE).
