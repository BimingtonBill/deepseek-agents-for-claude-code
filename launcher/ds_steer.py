"""Nudges for a running worker, the moment it starts to drift, instead of a hard stop later.

The launcher calls `watch` every 15 seconds while a worker runs. It reads the worker's transcript and,
the first time a sign of drift appears, queues a short message in the run folder (nudge.txt):

  steps     100, 150 and 200 steps with tools: cost grows with every step, since each re-reads the
            whole context (the costliest OpenSkyrim coders ran 220-300 steps)
  context   200k and 350k tokens of context
  refused   the same kind of shell command refused 3 times: that form isn't allowed, so stop retrying
  sleep     a sleep of 2 minutes or more (coders slept up to 9 minutes on background builds)

The worker's own PostToolUse hook runs `deliver` after every tool call: it hands any queued message
to the worker as added context and clears it, so the worker sees it before its next step. Every nudge
is also kept in steer.json, which tools/ds_morning.py reports.

    python ds_steer.py watch --transcript <file> --since <ISO time> --run-dir <folder>
    python ds_steer.py deliver --run-dir <folder>
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

DENIED = ('Permission for this tool use was denied', 'requires approval', 'was blocked')


def parse_time(text):
    t = dt.datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    return (t if t.tzinfo else t.astimezone()).astimezone(dt.timezone.utc)


def signals(transcript, since=None):
    """Steps with tools, latest context size, refused shell commands by their first word, and the
    longest sleep, in this launch of the worker."""
    steps, context, longest_sleep, slept = set(), 0, 0, 0
    commands, refused = {}, {}
    if not transcript or not os.path.exists(transcript):
        return dict(steps=0, context=0, refused={}, sleep=0, slept=0)
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
    return dict(steps=len(steps), context=context, refused=refused, sleep=longest_sleep, slept=slept)


def nudges(sig, fired):
    """The messages due now, as (key, text), skipping any already sent."""
    out = []
    for n in STEPS:
        if sig['steps'] >= n and 'steps%d' % n not in fired:
            text = {100: 'You have taken 100 steps. Each step re-reads everything so far, so the cost of every step keeps growing. Finish the part you are on, then write your report: what is done, what is left, and what you found.',
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


def watch(transcript, since, run_dir):
    run_dir = Path(run_dir)
    state_file = run_dir / 'steer.json'
    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {'nudges': []}
    fired = {n['key'] for n in state['nudges']}
    sig = signals(transcript, since)
    due = nudges(sig, fired)
    if not due:
        return []
    now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    with open(run_dir / 'nudge.txt', 'a', encoding='utf-8') as fh:
        for key, text in due:
            fh.write(text + '\n')
    state['nudges'] += [dict(key=k, at=now, steps=sig['steps'], context=sig['context'], text=t) for k, t in due]
    state_file.write_text(json.dumps(state, indent=1), encoding='utf-8')
    return due


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
    d = sub.add_parser('deliver')
    d.add_argument('--run-dir', required=True)
    a = ap.parse_args(argv)
    if a.cmd == 'watch':
        for key, _ in watch(a.transcript, parse_time(a.since), a.run_dir):
            print(key)
        return 0
    out = deliver(a.run_dir)
    if out:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
