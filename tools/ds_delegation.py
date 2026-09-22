"""The delegation level: how much Claude hands to DeepSeek workers, from 0 (never) to 10 (everything).

    python tools/ds_delegation.py                     the effective level here, where it comes from, and what it means
    python tools/ds_delegation.py --set 7             set it for this project (.deepseek-agents.json "delegation")
    python tools/ds_delegation.py --set 5 --global    set your default for every project (~/.claude-deepseek/config.json)
    python tools/ds_delegation.py --set 7 --agents-md also write the level's rules into this project's AGENTS.md
    python tools/ds_delegation.py --table             all eleven levels

Where the level comes from, first match wins: the DS_DELEGATION environment variable, the project's
.deepseek-agents.json, ~/.claude-deepseek/config.json, else 5.

The level steers Claude, not the workers, so Claude has to see it. The deepseek-agents skill reads it,
but the skill only loads when workers come up. --agents-md puts the rules in the project's AGENTS.md,
which Claude reads at the start of every session; without it, levels above 5 can't make Claude reach
for workers unprompted. The launcher enforces one thing itself: at level 0 it refuses to start a
worker unless it is given -Force (the user asked for one explicitly).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT = 5
GLOBAL_CONFIG = Path.home() / '.claude-deepseek' / 'config.json'
# Where tools/install-skill.ps1 puts this script.
INSTALLED_TOOL = Path.home() / '.claude' / 'skills' / 'deepseek-agents' / 'tools' / 'ds_delegation.py'
BEGIN = '<!-- ds-delegation:begin (managed by DeepSeek Workers/tools/ds_delegation.py; edit with --set) -->'
END = '<!-- ds-delegation:end -->'

# What Claude keeps at every level: quality does not scale down with the dial.
ALWAYS = ('At every level Claude keeps: talking to the user, design and architecture decisions, '
          'integration into the main checkout, security-sensitive changes, and review of every worker '
          'result it acts on (spot-check the claims that matter; read the full diff of any edit). '
          'Whenever workers are running, Claude works in parallel on something that cannot collide with '
          'them (the next brief, integration plumbing, the previous review, its own tests and builds), '
          'and starts its own long builds and conversions in the background too; a worker run is not '
          'a wait.')
# Shown in every generated AGENTS.md block, so every session sees it before it plans.
MISSING_TOOLS = ('Missing tools: before starting a job, check that the tools it needs are installed. If a compiler, '
                 'runtime or package the best approach needs is missing, stop and ask the user to install it (say '
                 'what it is for and give the exact install command) instead of working around it with a weaker '
                 'approach or a hand-written substitute. Continue without it only if the user chooses to.')

LEVELS = {
    0: ('Off', 'Claude does everything itself. Never launch a DeepSeek worker, not even an advisor. '
               'If the user explicitly asks for one, launch it with -Force.'),
    1: ('On request only', 'Use workers only when the user asks for them in this conversation.'),
    2: ('Rare', 'Suggest a worker when a task is a large read-only survey (many files, a big dump, '
                'long logs), but ask before launching.'),
    3: ('Big reads', 'Delegate large read-only research and surveys without asking: sweeping many '
                     'files, reading big dumps or logs, mapping unfamiliar code. Claude writes all code '
                     'and does all small lookups itself.'),
    4: ('Research and review', 'Delegate research of any size that takes more than a few searches, '
                               'plus independent reviews and analyses of finished runs. Claude writes '
                               'all code.'),
    5: ('Balanced (default)', 'Delegate research, reviews and run analyses by default. Delegate '
                              'bounded, self-contained implementation (a new parser, validator, tool or '
                              'test file with a fixed interface) through tools/ds_impl.ps1. Claude keeps '
                              'anything touching shared interfaces or more than a few files.'),
    6: ('Workers first for bounded work', 'As 5, and prefer a worker for any task that can be written as a '
                                          'standalone brief with a clear check, including documentation and '
                                          'test writing. Run independent tasks in parallel (about four at a '
                                          'time) with an independent reviewer on implementation.'),
    7: ('Claude plans and reviews', 'Claude plans, writes briefs, reviews and integrates; workers do the '
                                    'exploration and most coding, including multi-file changes in their own '
                                    'worktrees with owned-file lists. Use a DeepSeek lead (-CanSpawn) for jobs '
                                    'that split into independent parts, and -Crosstalk for workers whose work '
                                    'touches.'),
    8: ('Heavy delegation', 'As 7, and Claude avoids reading source itself beyond what review needs: '
                            'ask a worker to locate, summarize or trace code instead. Keep several workers '
                            'busy whenever there is independent work.'),
    9: ('Near-total', 'As 8, and delegate even small edits and lookups when a worker can do them while '
                      'Claude does something else. Claude writes code only to integrate or to fix a '
                      'worker result faster than a resume would.'),
    10: ('Everything', 'Claude only orchestrates: every task, however small, goes to a worker. Claude '
                       'reads briefs, reports and diffs, integrates, and talks to the user. If no worker '
                       'can do a step (it needs this conversation, a GUI, or the user), Claude does it '
                       'and says why.'),
}


def _project_root():
    """The project these tools act on. Run from the DeepSeek Workers harness or the installed skill,
    that is DS_PROJECT or the current folder. Copied into a project's tools/, it is DS_PROJECT or the
    folder above tools/, wherever it is run from."""
    if os.environ.get('DS_PROJECT'):
        return Path(os.environ['DS_PROJECT']).resolve()
    here = Path(__file__).resolve().parents[1]
    # The harness (launcher/ds-agent.ps1) or the installed skill (ds-agent.ps1 beside tools/): act on
    # the folder it is run from. Anywhere else, the tools sit in a project's tools/: act on that project.
    if (here / 'launcher' / 'ds-agent.ps1').exists() or (here / 'ds-agent.ps1').exists():
        return Path(os.getcwd()).resolve()
    return here


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _valid(value):
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return level if 0 <= level <= 10 else None


def effective(project, env=None, global_config=None):
    """(level, source) for a project folder."""
    env = os.environ if env is None else env
    global_config = GLOBAL_CONFIG if global_config is None else Path(global_config)
    level = _valid(env.get('DS_DELEGATION'))
    if level is not None:
        return level, 'DS_DELEGATION environment variable'
    config = _read_json(Path(project) / '.deepseek-agents.json') or {}
    level = _valid(config.get('delegation'))
    if level is not None:
        return level, str(Path(project) / '.deepseek-agents.json')
    config = _read_json(global_config) or {}
    level = _valid(config.get('delegation'))
    if level is not None:
        return level, str(global_config)
    return DEFAULT, 'default'


def describe(level):
    name, rule = LEVELS[level]
    return 'Delegation level %d of 10 - %s. %s' % (level, name, rule)


def set_level(path, level):
    """Write "delegation": level into a JSON config, keeping every other key and their order."""
    path = Path(path)
    data = _read_json(path) if path.exists() else {}
    if data is None:
        raise SystemExit('%s is not valid JSON; fix it first' % path)
    data['delegation'] = level
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def agents_block(level):
    return '\n'.join([
        BEGIN,
        '## DeepSeek delegation level: %d of 10 (%s)' % (level, LEVELS[level][0]),
        '',
        LEVELS[level][1],
        '',
        ALWAYS,
        '',
        MISSING_TOOLS,
        '',
        'This block is generated. Change the level with `python "%s" --set <0-10> --agents-md` '
        'from this folder, or ask Claude to. The full scale is in the deepseek-agents skill.'
        % INSTALLED_TOOL.as_posix(),
        END,
    ])


def write_agents_md(project, level):
    """Insert or replace the managed block near the top of AGENTS.md (after its first heading)."""
    path = Path(project) / 'AGENTS.md'
    text = path.read_text(encoding='utf-8') if path.exists() else '# Working in this project\n'
    block = agents_block(level)
    pattern = re.compile(re.escape(BEGIN) + r'.*?' + re.escape(END), re.S)
    if pattern.search(text):
        text = pattern.sub(lambda _: block, text, count=1)
    else:
        lines = text.split('\n')
        at = next((i + 1 for i, l in enumerate(lines) if l.startswith('# ')), 0)
        lines[at:at] = ['', block, '']
        text = '\n'.join(lines)
    path.write_text(text, encoding='utf-8')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--project', default=str(_project_root()))
    parser.add_argument('--set', type=int, choices=range(0, 11), metavar='0-10')
    parser.add_argument('--global', dest='is_global', action='store_true', help='with --set: your default for all projects')
    parser.add_argument('--agents-md', action='store_true', help="write the level's rules into the project's AGENTS.md")
    parser.add_argument('--table', action='store_true', help='print all levels')
    parser.add_argument('--brief', action='store_true', help='print only the one-line rule (for scripts)')
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()

    if args.table:
        for n in range(11):
            print('%2d  %-32s %s' % (n, LEVELS[n][0], LEVELS[n][1]))
        print('\n' + ALWAYS)
        return 0
    if args.set is not None:
        target = GLOBAL_CONFIG if args.is_global else project / '.deepseek-agents.json'
        set_level(target, args.set)
        print('set delegation %d in %s' % (args.set, target))
    level, source = effective(project)
    if args.agents_md:
        print('wrote the level-%d rules into %s' % (level, write_agents_md(project, level)))
    if args.brief:
        print(describe(level))
        return 0
    print('%s\n(from %s)\n\n%s' % (describe(level), source, ALWAYS))
    if source == 'DS_DELEGATION environment variable' and args.set is not None:
        print('\nNote: DS_DELEGATION is set and overrides the value just written.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
