"""Claude Code hook: every DeepSeek lead runs in the background with a watcher for its workers.

Registered by tools/install-skill.ps1 in ~/.claude/settings.json for the Bash and PowerShell tools:

    PreToolUse   a worker launch (ds-agent.ps1, or ds_impl.ps1 starting a coder) is refused unless it
                 runs in the background under a panel description in the house format,
                 "DeepSeek <kind> #<nnn>: <what>", so the panel says what each entry is. OpenSkyrim's
                 panel read "Launch the shadows worker" (2026-09-23), which hides the kind, the number
                 and the project.
    PostToolUse  after a lead starts, Claude is told the exact ds-watch.ps1 -Children command to start
                 next, so the lead's workers get their own Background tasks entries.

Remembering this was left to Claude and it was forgotten (lead-001-duck-photos.1 ran in the foreground,
with no panel entries for its three workers), so the hook makes it structural. Anything else passes
untouched, and any error here lets the tool call through: a broken hook must never block work.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path


def _adapter_dir():
    """The tools folder holding ds_state.py, the Python door to the launcher's state-dir rule. In the
    harness this hook is skill/deepseek-agents/ds_hook.py, with tools/ two folders up; installed as part
    of the skill it sits beside tools/ instead."""
    here = Path(__file__).resolve().parent
    for folder in (here.parents[1] / 'tools', here / 'tools'):
        if (folder / 'ds_state.py').is_file():
            return folder
    return None


_ADAPTER = _adapter_dir()
if _ADAPTER is not None:
    sys.path.insert(0, str(_ADAPTER))
    try:                                # a broken adapter must not stop the hook: the tool call goes through
        import ds_state
    except ImportError:
        ds_state = None
else:
    ds_state = None

WATCH = Path(__file__).resolve().parent / 'ds-watch.ps1'
KINDS = ('research', 'websearch', 'impl', 'review', 'analysis', 'critic', 'digest', 'advisor', 'lead',
         'selftest', 'probe')
# "DeepSeek <kind> #<nnn>: <what>", the panel format in the skill.
PANEL = re.compile(r'^DeepSeek (%s) #\d{3}(\.\d+)?: \S' % '|'.join(KINDS))


def without_heredocs(cmd):
    """The command with any here-document body removed. A script written into a file
    (python - <<PY ... PY) often contains a launch line as text: that is data, not a command."""
    out, terminator = [], None
    for line in cmd.split('\n'):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        out.append(line)
        m = re.search(r'<<-?\s*["\']?([A-Za-z_][A-Za-z_0-9]*)["\']?', line)
        if m:
            terminator = m.group(1)
    return '\n'.join(out)


SHELLS = ('powershell', 'powershell.exe', 'pwsh', 'pwsh.exe')
SCRIPTS = ('ds-agent.ps1', 'ds_impl.ps1')
MANAGEMENT = re.compile(r'^-(DryRun|List|Integrate|Discard|Post)$', re.I)


def _words(segment):
    """A segment split like a shell would, quotes kept together, so a path with a space is one word.
    posix=False keeps Windows backslashes; the quotes are stripped afterwards."""
    try:
        words = shlex.split(segment, posix=False)
    except ValueError:
        words = segment.split()
    return [w.strip('"\'') for w in words]


def launches_worker(cmd):
    """True when this command really starts a worker, rather than mentioning one.

    A segment counts when it runs the launcher or ds_impl itself: a PowerShell given the script as its
    -File (the path may contain spaces, and the shell may be a quoted full path), or the script invoked
    directly or with the call operator &. Text that merely contains the names (a grep pattern, a script
    being written in a here-document, a quoted message) does not count, nor do dry runs and ds_impl's
    management commands. Found by review-024: the first version split paths at their spaces, so any
    launch from a folder such as "DeepSeek Workers" went unchecked."""
    for segment in re.split(r'&&|\|\||;|\n', without_heredocs(cmd)):
        words = _words(segment)
        while words and re.match(r'^[A-Za-z_][A-Za-z_0-9]*=', words[0]):   # VAR=value prefixes
            words.pop(0)
        if words and words[0] == '&':
            words.pop(0)
        if not words:
            continue
        first = Path(words[0]).name.lower()
        if first in SHELLS:
            script = next((words[i + 1] for i, w in enumerate(words[:-1]) if w.lower() == '-file'), '')
        else:
            script = words[0]
        if Path(script).name.lower() not in SCRIPTS:
            continue
        if any(MANAGEMENT.match(w) for w in words):
            continue
        return True
    return False


def arg(cmd, name):
    """The value of -Name in a PowerShell command line, quoted or not."""
    m = re.search(r'-%s\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))' % name, cmd, re.I)
    return next((g for g in m.groups() if g), None) if m else None


def state_dir(cmd, cwd):
    """Where the launcher will keep the manifest, by its own rule (tools/ds_state.py, and behind it
    launcher/ds-state.ps1): DS_STATE_DIR, the project's stateDir, local/agents when local/ exists, else
    ~/.claude-deepseek/agents. DS_STATE_DIR written into the command itself is not the rule's - it is the
    value the launched process really gets - so the command is read for it first."""
    # Only an assignment that starts a command segment (bash VAR=value prefixes, export, or PowerShell's
    # $env:), never the same text inside an argument (audit finding SDR-20260924-03).
    m = re.search(r'(?:^|&&|\|\||;|\n)\s*(?:(?:export\s+)?(?:[A-Za-z_][A-Za-z_0-9]*=\S*\s+)*|\$env:)DS_STATE_DIR\s*=\s*'
                  r'(?:"([^"]+)"|\'([^\']+)\'|([^\s;]+))', cmd)
    if m:
        return next(g for g in m.groups() if g)
    if ds_state is None:
        raise RuntimeError('ds_state.py not found beside this hook or two folders up')
    return str(ds_state.state_dir(Path(arg(cmd, 'Dir') or cwd)))


def session_start(event):
    """The short morning report, as context for a session that opens in a project where workers ran
    since the last report. Silent everywhere else."""
    import subprocess
    cwd = event.get('cwd') or os.getcwd()
    here = Path(__file__).resolve().parent
    # tools/ beside this file once installed; the harness keeps it two folders up.
    morning = next((p for p in (here / 'tools' / 'ds_morning.py', here.parents[1] / 'tools' / 'ds_morning.py') if p.is_file()), None)
    if not morning or not (Path(cwd) / 'local').is_dir() and not os.environ.get('DS_STATE_DIR'):
        return
    try:
        done = subprocess.run([sys.executable, str(morning), '--project', cwd, '--short'], capture_output=True,
                              text=True, encoding='utf-8', errors='replace', timeout=12)
    except (OSError, subprocess.SubprocessError):
        return
    text = done.stdout.strip()
    if done.returncode == 0 and text:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': text}}))


def main():
    event = json.load(sys.stdin)
    if event.get('hook_event_name') == 'SessionStart':
        session_start(event)
        return
    if event.get('tool_name') not in ('Bash', 'PowerShell'):
        return
    tool_input = event.get('tool_input') or {}
    cmd = str(tool_input.get('command') or tool_input.get('script') or '')
    if not launches_worker(cmd):
        return
    label = (arg(cmd, 'Label') or arg(cmd, 'Name')
             or (Path(arg(cmd, 'TaskFile') or arg(cmd, 'Brief')).stem if (arg(cmd, 'TaskFile') or arg(cmd, 'Brief')) else None)
             or 'task')
    hook = event.get('hook_event_name')

    # The panel is how a human sees what is running, so every worker entry names its kind and number.
    if hook == 'PreToolUse' and not PANEL.match(str(tool_input.get('description') or '')):
        kind, number = 'research', '001'
        parts = label.split('-')
        if parts and parts[0] in KINDS:
            kind = parts[0]
            if len(parts) > 1 and parts[1].isdigit():
                number = parts[1].zfill(3)
        what = ' '.join(parts[2:]) if len(parts) > 2 else (label if kind == 'research' else 'what it does')
        tail = ' (lead, spawns workers)' if re.search(r'-CanSpawn\b', cmd, re.I) else ''
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                'A worker launch needs a Background tasks description in the house format, so the panel '
                'says what the entry is: "DeepSeek %s #%s: %s"%s. Run the same command again with that '
                'description (and run_in_background true).' % (kind, number, what, tail)),
        }}))
        return

    if hook == 'PreToolUse' and not tool_input.get('run_in_background'):
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                'A DeepSeek worker must run in the background, so it appears in the Background tasks panel '
                'and you can keep working while it runs. Run the same command again with run_in_background '
                'true. For a lead, this hook then gives you the watcher command to start straight after.'),
        }}))
        return

    if hook == 'PostToolUse' and re.search(r'-CanSpawn\b', cmd, re.I):
        folder = state_dir(cmd, event.get('cwd') or os.getcwd())
        shell_var = re.search(r'[$%]', folder)
        watch = 'powershell -NoProfile -ExecutionPolicy Bypass -File "%s" -Children %s -StateDir "%s"' % (
            WATCH.as_posix(), label, folder if shell_var else Path(folder).as_posix())
        # The launch set the state folder through a shell variable, which this hook can't expand.
        unexpanded = ('\nThe -StateDir above contains a shell variable (%s); replace it with the real folder '
                      'before running the watcher.' % folder) if shell_var else ''
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': (
                'DeepSeek lead %s started. Start its watcher now, in the background (run_in_background true), '
                'before anything else, with the description "Watch lead #<nnn> for new workers":\n%s\n'
                'When it exits, start each ds-watch.ps1 -Run command it prints, in the background with the '
                'description it prints. If the lead is still running, also restart the printed -Children ... '
                '-Known ... command. Don\'t block in the foreground while the lead runs.%s' % (label, watch, unexpanded)),
        }}))


def install(settings_path=None):
    """Register this hook in ~/.claude/settings.json, replacing an earlier registration of it and keeping
    every other setting. The file is backed up to ~/.claude-deepseek/backups first."""
    import shutil, time
    path = Path(settings_path) if settings_path else Path.home() / '.claude' / 'settings.json'
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding='utf-8') or '{}')
        except ValueError:
            print('hook not registered: %s is not valid JSON' % path)
            return 1
        backups = Path.home() / '.claude-deepseek' / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backups / ('settings.json.bak-%s' % time.strftime('%Y%m%d-%H%M%S')))
    # Hook commands run in Git Bash or PowerShell; a bare first word works in both, a quoted path only in bash.
    runner = 'python' if shutil.which('python') else ('py' if shutil.which('py') else Path(sys.executable).as_posix())
    command = '%s "%s"' % (runner, Path(__file__).resolve().as_posix())
    if not isinstance(settings, dict) or not isinstance(settings.get('hooks', {}), dict):
        print('hook not registered: %s does not hold a settings object (audit finding WLH-20260924-01)' % path)
        return 1
    hooks = settings.setdefault('hooks', {})

    def without_ours(groups):
        # Drop only this hook's own entries: a group the user also put other hooks in keeps them
        # (audit finding WORKERLA-20260924-01: whole groups used to be dropped).
        out = []
        for g in groups if isinstance(groups, list) else []:
            if not isinstance(g, dict) or not isinstance(g.get('hooks'), list):
                out.append(g)             # not ours to judge: keep it exactly as it was
                continue
            entries = [h for h in g['hooks'] if not (isinstance(h, dict) and 'ds_hook.py' in str(h.get('command', '')))]
            if entries:
                out.append(dict(g, hooks=entries))
            elif not g['hooks']:
                out.append(g)
        return out

    for event, matcher, timeout in (('PreToolUse', 'Bash|PowerShell', 10), ('PostToolUse', 'Bash|PowerShell', 10),
                                    ('SessionStart', 'startup|resume', 15)):
        hooks[event] = without_ours(hooks.get(event, [])) + [
            {'matcher': matcher, 'hooks': [{'type': 'command', 'command': command, 'timeout': timeout}]}]
    path.parent.mkdir(parents=True, exist_ok=True)
    # Through a temp file, so an interrupted write can't leave the user's settings half-written (review-049).
    tmp = path.with_name(path.name + '.ds-hook.tmp')
    tmp.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
    os.replace(str(tmp), str(path))
    print('registered the DeepSeek lead hook in %s (new sessions pick it up)' % path)
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--install':
        sys.exit(install(sys.argv[2] if len(sys.argv) > 2 else None))
    try:
        main()
    except Exception:  # never block a tool call because the hook itself failed
        pass
    sys.exit(0)
