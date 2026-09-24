"""The launcher's state-dir rule, for Python callers: ask the one script that holds it.

    import ds_state
    folder = ds_state.state_dir(project)      # project defaults to the current folder

launcher/ds-state.ps1 is the rule: DS_STATE_DIR, else the project's .deepseek-agents.json "stateDir"
(absolute as-is, otherwise joined onto the project), else <project>/local/agents when <project>/local
exists, else ~/.claude-deepseek/agents. This module runs that script and returns what it printed, so no
Python caller keeps a second copy of the rule. fallback_dir() below is that second copy - one small
function, used only when the script cannot be found or does not answer.
"""
import json
import os
import subprocess
from pathlib import Path


def _script():
    """launcher/ds-state.ps1, found the way the tools find ds-agent.ps1: in the harness it is beside the
    launcher, <harness>/launcher/; installed as part of the skill the launcher's files sit beside tools/;
    anywhere else the tools were copied into a project's tools/ and the launcher is the installed
    skill's."""
    root = Path(__file__).resolve().parents[1]
    for candidate in (root / 'launcher' / 'ds-state.ps1', root / 'ds-state.ps1',
                      Path.home() / '.claude' / 'skills' / 'deepseek-agents' / 'ds-state.ps1'):
        if candidate.is_file():
            return candidate
    return None


def state_dir(project=None):
    """The state dir for a project (default: the current folder), by the launcher's rule. Absolute."""
    project = Path(project) if project is not None else Path.cwd()
    script = _script()
    if script is not None:
        try:
            done = subprocess.run(
                ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                 '-Dir', str(project)],
                capture_output=True, encoding='utf-8-sig', errors='replace', timeout=60)
            printed = [line.strip() for line in (done.stdout or '').splitlines() if line.strip()]
            if done.returncode == 0 and printed:
                return Path(printed[0])
        except (OSError, subprocess.SubprocessError):
            pass
    return fallback_dir(project)


def fallback_dir(project=None, env=None):
    """The rule in Python, for when launcher/ds-state.ps1 cannot be run. A caller that passes env (a
    mapping) wants the answer for that environment rather than this process's."""
    project = Path(project) if project is not None else Path.cwd()
    env = os.environ if env is None else env
    if env.get('DS_STATE_DIR'):
        # The script makes it absolute with GetFullPath (audit finding SDR-20260924-05).
        return Path(os.path.abspath(env['DS_STATE_DIR']))
    try:
        configured = json.loads((project / '.deepseek-agents.json').read_text(encoding='utf-8')).get('stateDir')
    except (OSError, ValueError, AttributeError):
        configured = None
    if configured:
        # The script stringifies whatever is there ({"stateDir": 123} -> <project>\123); do the same rather
        # than raise (audit finding SDR-20260924-01).
        # PowerShell's [string] joins a list with spaces (audit finding SDR-20260924-04).
        configured = Path(' '.join(map(str, configured)) if isinstance(configured, list) else str(configured))
        return configured if configured.is_absolute() else project / configured
    if (project / 'local').is_dir():
        return project / 'local' / 'agents'
    return Path.home() / '.claude-deepseek' / 'agents'
