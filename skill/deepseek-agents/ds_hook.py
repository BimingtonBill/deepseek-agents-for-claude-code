"""Claude Code hook: every DeepSeek lead runs in the background with a watcher for its workers.

Registered by tools/install-skill.ps1 in ~/.claude/settings.json for the Bash and PowerShell tools:

    PreToolUse   a launch of ds-agent.ps1 with -CanSpawn that is not run in the background is refused,
                 with the reason, so Claude re-runs it in the background under a panel description.
    PostToolUse  after a lead starts, Claude is told the exact ds-watch.ps1 -Children command to start
                 next, so the lead's workers get their own Background tasks entries.

Remembering this was left to Claude and it was forgotten (lead-001-duck-photos.1 ran in the foreground,
with no panel entries for its three workers), so the hook makes it structural. Anything else passes
untouched, and any error here lets the tool call through: a broken hook must never block work.
"""
import json
import os
import re
import sys
from pathlib import Path

WATCH = Path(__file__).resolve().parent / 'ds-watch.ps1'


def arg(cmd, name):
    """The value of -Name in a PowerShell command line, quoted or not."""
    m = re.search(r'-%s\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))' % name, cmd, re.I)
    return next((g for g in m.groups() if g), None) if m else None


def state_dir(cmd, cwd):
    """Where the launcher will keep the manifest, by its own rule: DS_STATE_DIR, the project's stateDir,
    local/agents when local/ exists, else ~/.claude-deepseek/agents."""
    m = re.search(r'DS_STATE_DIR\s*=\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s;]+))', cmd)
    if m:
        return next(g for g in m.groups() if g)
    project = Path(arg(cmd, 'Dir') or cwd)
    try:
        configured = json.loads((project / '.deepseek-agents.json').read_text(encoding='utf-8')).get('stateDir')
    except (OSError, ValueError, AttributeError):
        configured = None
    if configured:
        return str(project / configured) if not os.path.isabs(configured) else configured
    if (project / 'local').is_dir():
        return str(project / 'local' / 'agents')
    return str(Path.home() / '.claude-deepseek' / 'agents')


def main():
    event = json.load(sys.stdin)
    if event.get('tool_name') not in ('Bash', 'PowerShell'):
        return
    tool_input = event.get('tool_input') or {}
    cmd = str(tool_input.get('command') or tool_input.get('script') or '')
    if 'ds-agent.ps1' not in cmd or not re.search(r'-CanSpawn\b', cmd, re.I) or re.search(r'-DryRun\b', cmd, re.I):
        return
    label = arg(cmd, 'Label') or (Path(arg(cmd, 'TaskFile')).stem if arg(cmd, 'TaskFile') else None) or 'task'
    hook = event.get('hook_event_name')

    if hook == 'PreToolUse' and not tool_input.get('run_in_background'):
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                'A DeepSeek lead must run in the background, so that it and its workers appear in the '
                'Background tasks panel. Run the same command again with run_in_background true and the '
                'description "DeepSeek lead #<nnn>: <what> (lead, spawns workers)". This hook will then give '
                'you the watcher command to start straight after.'),
        }}))
        return

    if hook == 'PostToolUse':
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
    hooks = settings.setdefault('hooks', {})
    for event in ('PreToolUse', 'PostToolUse'):
        kept = [g for g in hooks.get(event, []) if not any('ds_hook.py' in str(h.get('command', '')) for h in g.get('hooks', []))]
        kept.append({'matcher': 'Bash|PowerShell', 'hooks': [{'type': 'command', 'command': command, 'timeout': 10}]})
        hooks[event] = kept
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
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
