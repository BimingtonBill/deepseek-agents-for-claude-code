"""Nudges for a running worker, the moment it starts to drift, instead of a hard stop later.

The launcher calls `watch` every 15 seconds while a worker runs. It reads the worker's transcript and,
the first time a sign of drift appears, queues a short message in the run folder (nudge.txt):

  steps     100, 150 and 200 steps with tools: cost grows with every step, since each re-reads the
            whole context (the costliest OpenSkyrim coders ran 220-300 steps)
  context   200k and 350k tokens of context
  refused   the same kind of shell command refused 3 times: that form isn't allowed, so stop retrying
  sleep     a sleep of 2 minutes or more (coders slept up to 9 minutes on background builds)

  budget    past 1.5 and 2 times the steps its kind usually takes (the step budget), when that comes
            before the fixed counts: a review usually takes about 11 steps, so one at 90 is far off
            track while the fixed nudges would still say nothing
The worker's own PostToolUse hook runs `deliver` after every tool call: it hands any queued message
to the worker as added context and clears it, so the worker sees it before its next step. Every nudge
is also kept in steer.json, which tools/ds_morning.py reports.

The step budget is learned: ds_spend.py records each finished run's steps, and `budget` gives the median
of the kind's last 30 runs (DEFAULT_BUDGET until there are 5). The launcher tells the worker its budget up
front. Each `watch` also writes progress.json in the run folder (steps, tool uses, context, what it is
doing now), so Claude can see how a running worker is going without reading its output: `progress`.

    python ds_steer.py watch --transcript <file> --since <ISO time> --run-dir <folder> [--budget N]
    python ds_steer.py deliver --run-dir <folder>
    python ds_steer.py budget --kind impl [--spend-dir <folder>]
    python ds_steer.py progress [--state-dir <folder>]      the running workers, one line each
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

STEPS = (100, 150, 200)
CONTEXT = (200_000, 350_000)
REFUSED_AFTER = 3
SLEEP_AT = 120
# Steps a kind usually takes, until the spend record holds 5 runs of it with their steps.
DEFAULT_BUDGET = dict(review=20, critic=20, websearch=20, digest=40, probe=15, selftest=15, advisor=40,
                      research=60, analysis=60, lead=60, impl=80)
BUDGET_RUNS = 30
BUDGET_MAX = 80        # never tell a worker ~100 steps is normal: briefs should finish well under 100

DENIED = ('Permission for this tool use was denied', 'requires approval', 'was blocked')


def parse_time(text):
    t = dt.datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    return (t if t.tzinfo else t.astimezone()).astimezone(dt.timezone.utc)


def signals(transcript, since=None):
    """Steps with tools, latest context size, refused shell commands by their first word, and the
    longest sleep, in this launch of the worker."""
    steps, context, longest_sleep, slept = set(), 0, 0, 0
    commands, refused = {}, {}
    tools, now = 0, ''
    if not transcript or not os.path.exists(transcript):
        return dict(steps=0, context=0, refused={}, sleep=0, slept=0, tools=0, now='')
    with open(transcript, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if '"tool_use"' not in line and '"tool_result"' not in line and '"usage"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if since and e.get('timestamp') and parse_time(e['timestamp']) < since:
                continue
            msg = e.get('message') or {}
            us = msg.get('usage')
            if isinstance(us, dict):
                context = (us.get('input_tokens') or 0) + (us.get('cache_read_input_tokens') or 0) + \
                          (us.get('cache_creation_input_tokens') or 0)
            for c in msg.get('content') or []:
                if not isinstance(c, dict):
                    continue
                if c.get('type') == 'tool_use':
                    steps.add(msg.get('id') or c.get('id'))
                    tools += 1
                    now = describe_tool(c.get('name'), c.get('input') or {})
                    if c.get('name') == 'Bash':
                        cmd = (c.get('input') or {}).get('command') or ''
                        commands[c.get('id')] = cmd
                        m = re.match(r'\s*sleep\s+(\d+)', cmd)
                        if m:
                            longest_sleep = max(longest_sleep, int(m.group(1)))
                            slept += int(m.group(1))
                elif c.get('type') == 'tool_result' and c.get('is_error') and c.get('tool_use_id') in commands:
                    body = c.get('content')
                    body = body if isinstance(body, str) else json.dumps(body)
                    if any(d in body for d in DENIED):
                        words = re.findall(r'[\w./-]+', commands[c['tool_use_id']])
                        # "cargo fmt", "git grep", "python -c" are forms of their own; cd's argument is a path.
                        head = ' '.join(words[:2]) if len(words) > 1 and words[0] in ('git', 'cargo', 'python', 'npm') else (words[0] if words else '?')
                        refused[head] = refused.get(head, 0) + 1
    return dict(steps=len(steps), context=context, refused=refused, sleep=longest_sleep, slept=slept, tools=tools, now=now)


def describe_tool(name, inp):
    """'Bash cargo test -p portal', 'Read src/door.rs', 'Grep load_door': what a tool call is doing."""
    detail = (inp.get('command') or inp.get('file_path') or inp.get('pattern') or inp.get('query') or inp.get('url')
              or inp.get('description') or '')
    detail = ' '.join(str(detail).split())
    if inp.get('file_path'):
        detail = '/'.join(Path(detail).parts[-2:])
    return ('%s %s' % (name, detail)).strip()[:80]


def budget(kind, spend_dir=None):
    """The steps a worker of this kind usually takes: the median of its last BUDGET_RUNS real recorded runs
    (5+ steps, 2+ cents), rounded up to 5, between 10 and BUDGET_MAX, once there are 5; else DEFAULT_BUDGET."""
    d = Path(spend_dir or os.environ.get('DS_SPEND_DIR') or Path.home() / '.claude-deepseek' / 'spend')
    seen = []
    try:
        with open(d / 'spend.jsonl', encoding='utf-8') as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                # Trivial runs (harness probes, failed starts) would drag the median down to a few steps.
                if (isinstance(r, dict) and r.get('kind') == kind and isinstance(r.get('steps'), int)
                        and r['steps'] >= 5 and (r.get('cost') or 0) >= 0.02):
                    seen.append(r['steps'])
    except OSError:
        pass
    seen = seen[-BUDGET_RUNS:]
    if len(seen) < 5:
        return DEFAULT_BUDGET.get(kind, 60)
    seen.sort()
    mid = seen[len(seen) // 2] if len(seen) % 2 else (seen[len(seen) // 2 - 1] + seen[len(seen) // 2]) / 2
    return min(BUDGET_MAX, max(10, int(-(-mid // 5) * 5)))


def nudges(sig, fired, step_budget=None):
    """The messages due now, as (key, text), skipping any already sent."""
    out = []
    if step_budget:
        # Relative to what this kind usually takes, where that comes before the fixed counts below.
        for mult, key in ((1.5, 'budget150'), (2.0, 'budget200')):
            at = int(step_budget * mult)
            if sig['steps'] >= at and at < STEPS[0] and key not in fired:
                out.append((key, (
                    'You are at %d steps; tasks like this usually take about %d. Finish the part you are on and '
                    'write your report now: what is done, what is left, and what you found.' if mult < 2 else
                    'You are at %d steps, twice the %d this kind of task usually takes. Stop here and report: what '
                    'is done, what is left, and what you found. Claude will brief the rest separately.')
                    % (sig['steps'], step_budget)))
    for n in STEPS:
        if sig['steps'] >= n and 'steps%d' % n not in fired:
            # Firmer than it was: a coder read "finish the part you are on" as leave to carry on (2026-09-25).
            text = {100: 'You have taken 100 steps. Stop exploring now. Finish only the change already in hand, then write your report: what is done, what is left, and what you found. Every further step re-reads everything so far and costs more than the last.',
                    150: 'You are at 150 steps. Wrap up now: stop exploring, finish or back out the change in hand, and report what is done and what is left.',
                    200: 'You are at 200 steps, well past what this task should take. Report now with what you have; Claude will split the rest into smaller tasks.'}[n]
            out.append(('steps%d' % n, text))
    for n in CONTEXT:
        if sig['context'] >= n and 'context%d' % n not in fired:
            out.append(('context%d' % n, 'Your context is %dk tokens and every step re-reads all of it. Read nothing more in full: search, or read only the lines you need, and head for your report.' % (n // 1000)))
    for head, count in sig['refused'].items():
        key = 'refused:' + head
        if count >= REFUSED_AFTER and key not in fired:
            out.append((key, 'Shell commands starting "%s" have been refused %d times: that form is not allowed here and retrying will not change it. Use a form from your list of allowed commands (no cd, no chains, no python -c), or write a small script and run it.' % (head, count)))
    if sig['sleep'] >= SLEEP_AT and 'sleep' not in fired:
        out.append(('sleep', 'Don\'t sleep for minutes at a time: a sleep cannot end early when a build finishes. Run builds and tests in the foreground with the Bash timeout raised (up to 600000 ms); for a longer job, check on it about once a minute.'))
    return out


def watch(transcript, since, run_dir, step_budget=None):
    run_dir = Path(run_dir)
    state_file = run_dir / 'steer.json'
    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {'nudges': []}
    fired = {n['key'] for n in state['nudges']}
    sig = signals(transcript, since)
    write_progress(run_dir, sig, since, step_budget)
    due = nudges(sig, fired, step_budget)
    if not due:
        return []
    now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    with open(run_dir / 'nudge.txt', 'a', encoding='utf-8') as fh:
        for key, text in due:
            fh.write(text + '\n')
    state['nudges'] += [dict(key=k, at=now, steps=sig['steps'], context=sig['context'], text=t) for k, t in due]
    state_file.write_text(json.dumps(state, indent=1), encoding='utf-8')
    return due


def write_progress(run_dir, sig, since, step_budget=None):
    """progress.json: how the running worker is going, for Claude and `progress`."""
    now = dt.datetime.now().astimezone()
    try:
        secs = int((now - since).total_seconds()) if since else None
        row = dict(updated=now.isoformat(timespec='seconds'), seconds=secs, steps=sig['steps'], tools=sig['tools'],
                   context=sig['context'], now=sig['now'], budget=step_budget)
        tmp = Path(run_dir) / 'progress.json.tmp'
        tmp.write_text(json.dumps(row), encoding='utf-8')
        os.replace(str(tmp), str(Path(run_dir) / 'progress.json'))
    except (OSError, TypeError):
        pass


def progress_lines(state_dir):
    """One line per running worker in this state dir, from its progress.json."""
    out = []
    for mf in sorted(Path(state_dir).glob('runs/*/manifest.json')):
        try:
            m = json.loads(mf.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        if m.get('state') != 'working' or m.get('provider') == 'claude':
            continue
        try:
            p = json.loads((mf.parent / 'progress.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            out.append('%s: starting' % m['run_id'])
            continue
        mins, secs = divmod(p.get('seconds') or 0, 60)
        over = ' (budget %d)' % p['budget'] if p.get('budget') else ''
        out.append('%s: %dm%02ds, %d steps%s, %d tool uses, context %dk, now: %s' % (
            m['run_id'], mins, secs, p.get('steps', 0), over, p.get('tools', 0), (p.get('context') or 0) // 1000,
            p.get('now') or '-'))
    return out


def deliver(run_dir):
    """Hand any queued nudge to the worker as added context (PostToolUse hook), then clear it."""
    f = Path(run_dir) / 'nudge.txt'
    try:
        text = f.read_text(encoding='utf-8').strip()
        f.unlink()
    except OSError:
        return None
    if not text:
        return None
    return json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse',
                                              'additionalContext': 'Note from the launcher: ' + text}})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    w = sub.add_parser('watch')
    w.add_argument('--transcript', required=True); w.add_argument('--since', required=True); w.add_argument('--run-dir', required=True)
    w.add_argument('--budget', type=int, help="the steps this worker's kind usually takes")
    d = sub.add_parser('deliver')
    d.add_argument('--run-dir', required=True)
    b = sub.add_parser('budget')
    b.add_argument('--kind', required=True); b.add_argument('--spend-dir')
    p = sub.add_parser('progress')
    p.add_argument('--state-dir', help='default: this folder\'s state dir (tools/ds_state.py)')
    a = ap.parse_args(argv)
    if a.cmd == 'watch':
        for key, _ in watch(a.transcript, parse_time(a.since), a.run_dir, a.budget):
            print(key)
        return 0
    if a.cmd == 'budget':
        print(budget(a.kind, a.spend_dir))
        return 0
    if a.cmd == 'progress':
        sd = a.state_dir
        if not sd:
            here = Path(__file__).resolve().parent
            sys.path[:0] = [str(here / 'tools'), str(here.parent / 'tools')]
            import ds_state
            sd = ds_state.state_dir(Path.cwd())
        print('\n'.join(progress_lines(sd)) or 'No DeepSeek workers running.')
        return 0
    out = deliver(a.run_dir)
    if out:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
