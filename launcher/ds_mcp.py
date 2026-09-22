"""The worker-side tools for crosstalk and hierarchy, as a tiny stdio MCP server (no dependencies).

ds-agent.ps1 starts this for a worker with crosstalk on (the default) or -CanSpawn. Tools reach the model as
mcp__dsw__<name>, and an MCP tool is allowed by its exact name, so no shell command has to match a
permission rule (a rule is matched against the literal command, and quoted paths with spaces never
matched reliably).

Tools, depending on DS_MCP_TOOLS (comma-separated):
  wait     wait_for_messages(seconds)          pause so a sibling's message can arrive between tool calls
  spawn    write_brief(name, content)          save a brief for a worker of your own
           spawn_workers(briefs, ...)          run those workers in parallel, wait, return their reports
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ENABLED = {t.strip() for t in os.environ.get('DS_MCP_TOOLS', '').split(',') if t.strip()}
BRIEF_DIR = Path(os.environ.get('DS_BRIEF_DIR', '.'))
SPAWN = os.environ.get('DS_SPAWN_SCRIPT', '')
WORK_DIR = os.environ.get('DS_WORK_DIR', os.getcwd())
KINDS = ('research', 'impl', 'review', 'analysis', 'critic', 'digest')

TOOLS = []
if 'wait' in ENABLED:
    TOOLS.append({
        'name': 'wait_for_messages',
        'description': ('Pause for a number of seconds (1-60) so a message from a sibling worker can arrive. '
                        'Messages are delivered between tool calls, so call this when you have nothing to do '
                        'but wait for a peer. Returns when the time is up.'),
        'inputSchema': {'type': 'object', 'properties': {'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 60}},
                        'required': ['seconds']},
    })
if 'spawn' in ENABLED:
    TOOLS.append({
        'name': 'write_brief',
        'description': ('Save a brief for a DeepSeek worker you will launch with spawn_workers. name is '
                        '<kind>-<nnn>-<slug> with kind one of %s and nnn a three-digit number you assign in order '
                        '(001, 002, ...), e.g. research-001-rc-rule; the worker\'s run id will be <name>.1. '
                        'content is the whole brief in Markdown with # Goal, # Context, # Scope, # Done when and '
                        '# Report sections. The worker sees only this text.' % ', '.join(KINDS)),
        'inputSchema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'content': {'type': 'string'}},
                        'required': ['name', 'content']},
    })
    TOOLS.append({
        'name': 'spawn_workers',
        'description': ('Launch up to 6 DeepSeek workers in parallel from briefs saved with write_brief, wait '
                        'for all of them, and return each report under its run id. Workers run read-only in '
                        'your working directory. They can message each other unless you set crosstalk false; '
                        'tell each one the others\' run ids in its brief. This can take many minutes.'),
        'inputSchema': {'type': 'object', 'properties': {
            'briefs': {'type': 'array', 'items': {'type': 'string'}, 'description': 'brief names given to write_brief'},
            'crosstalk': {'type': 'boolean', 'description': 'let the workers message each other; default true'},
            'effort': {'type': 'string', 'enum': ['low', 'high', 'max'], 'description': 'DeepSeek thinking depth; default high'},
            'max_turns': {'type': 'integer', 'minimum': 5, 'maximum': 200},
        }, 'required': ['briefs']},
    })


def brief_name_used(name):
    """True when the shared manifest already has a run of this task id."""
    manifest = Path(os.environ.get('DS_STATE_DIR', '')) / 'manifest.jsonl'
    if not os.environ.get('DS_STATE_DIR') or not manifest.exists():
        return False
    needle = '"task_id":"%s"' % name
    with open(manifest, encoding='utf-8') as handle:
        return any(needle in line for line in handle)


def text(result, error=False):
    return {'content': [{'type': 'text', 'text': result}], 'isError': error}


def call(name, args):
    if name == 'wait_for_messages' and 'wait' in ENABLED:
        seconds = max(1, min(60, int(args.get('seconds') or 15)))
        time.sleep(seconds)
        return text('waited %d s' % seconds)
    if name == 'write_brief' and 'spawn' in ENABLED:
        brief = str(args.get('name') or '').strip()
        if brief.endswith('.md'):
            brief = brief[:-3]
        if not re.fullmatch(r'(%s)-\d{3}-[a-z0-9][a-z0-9-]{1,60}' % '|'.join(KINDS), brief):
            return text('name must be <kind>-<nnn>-<slug> in lower case (e.g. research-001-rc-rule), kind one of %s' % ', '.join(KINDS), True)
        # The run id is <name>.<attempt>, counted across the whole manifest. A name used before would run
        # as .2 or later, and a sibling told "<name>.1" could not reach it (probe lead-006-watch-probe.1).
        if brief_name_used(brief):
            return text('the name %s was already used by an earlier run, so it would not run as %s.1; '
                        'choose another name' % (brief, brief), True)
        content = str(args.get('content') or '')
        if len(content) < 80 or '# Goal' not in content:
            return text('the brief needs at least a # Goal section and enough detail to stand alone', True)
        BRIEF_DIR.mkdir(parents=True, exist_ok=True)
        path = BRIEF_DIR / (brief + '.md')
        path.write_text(content, encoding='utf-8')
        return text('saved %s (run id will be %s.1)' % (path, brief))
    if name == 'spawn_workers' and 'spawn' in ENABLED:
        names = [str(b).strip().removesuffix('.md') for b in (args.get('briefs') or []) if str(b).strip()]
        if not names:
            return text('no briefs given', True)
        missing = [n for n in names if not (BRIEF_DIR / (n + '.md')).exists()]
        if missing:
            return text('not saved with write_brief yet: %s' % ', '.join(missing), True)
        cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', SPAWN, '-Dir', WORK_DIR,
               '-Briefs', ','.join(str(BRIEF_DIR / (n + '.md')) for n in names),
               '-Effort', args.get('effort') or 'high', '-MaxTurns', str(args.get('max_turns') or 80)]
        if args.get('crosstalk') is False:
            cmd.append('-NoCrosstalk')
        done = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = (done.stdout or '') + (('\n' + done.stderr) if done.stderr.strip() else '')
        # The children's first stdout line is Claude Code's model notice; it is noise here.
        out = '\n'.join(l for l in out.splitlines() if not l.startswith('[claude-code:unrecognized_model]'))
        return text(out.strip() or '(no output)', done.returncode not in (0, 1))
    return text('unknown tool %s' % name, True)


def reply(msg_id, result=None, error=None):
    body = {'jsonrpc': '2.0', 'id': msg_id}
    if error is not None:
        body['error'] = error
    else:
        body['result'] = result
    sys.stdout.write(json.dumps(body) + '\n')
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, msg_id = msg.get('method'), msg.get('id')
        if msg_id is None:
            continue  # notifications (initialized, cancelled) need no answer
        if method == 'initialize':
            reply(msg_id, {'protocolVersion': (msg.get('params') or {}).get('protocolVersion', '2025-06-18'),
                           'capabilities': {'tools': {}},
                           'serverInfo': {'name': 'dsw', 'version': '1.0'}})
        elif method == 'tools/list':
            reply(msg_id, {'tools': TOOLS})
        elif method == 'tools/call':
            params = msg.get('params') or {}
            try:
                reply(msg_id, call(params.get('name'), params.get('arguments') or {}))
            except Exception as exc:  # report, never crash the worker's tool server
                reply(msg_id, text('tool failed: %s' % exc, True))
        elif method == 'ping':
            reply(msg_id, {})
        else:
            reply(msg_id, error={'code': -32601, 'message': 'method not found: %s' % method})


if __name__ == '__main__':
    main()
