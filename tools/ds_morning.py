"""The morning report: what the workers did while nobody was watching, and what needs attention.

Reads only local files (manifests, transcripts, the spend record), so it costs nothing to run.

    python ds_morning.py                 everything since the last report (or the last 24 hours)
    python ds_morning.py --since 2026-09-23T17:00
    python ds_morning.py --short         a few lines, for the start of a session (ds_hook.py uses this)

It reports runs that failed, timed out or were stopped; long runs (100+ steps); time spent sleeping;
refused commands; nudges sent; the costliest runs; spend against the limit; and whether the project map
or pitfalls are due for a refresh. The full report is also saved in <state dir>/reports/.
"""
import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for extra in (HERE.parent / 'launcher', HERE.parent):   # the harness, or the installed skill
    if (extra / 'ds_steer.py').is_file():
        sys.path.insert(0, str(extra))
        break
from ds_state import state_dir  # noqa: E402
import ds_memory  # noqa: E402
import ds_audit  # noqa: E402

try:
    import ds_steer
    import ds_spend
except ImportError:   # an old install without them: report what the manifests say
    ds_steer = ds_spend = None
try:
    import ds_claude
except ImportError:
    ds_claude = None

LONG_STEPS = 100
SLEEP_WORTH = 300


def local(ts):
    return dt.datetime.fromisoformat(ts).astimezone()


def runs_since(sd, since):
    out = []
    for mf in (sd / 'runs').glob('*/manifest.json'):
        try:
            m = json.loads(mf.read_text(encoding='utf-8-sig'))
        except ValueError:
            continue
        stamp = m.get('ended') or m.get('started')
        if not stamp or local(stamp) < since:
            continue
        out.append(m)
    return sorted(out, key=lambda m: m.get('started') or '')


def analyse(sd, runs):
    costs = {}
    if ds_spend:
        for r in ds_spend.ledger(ds_spend.spend_dir()):
            key = (r.get('project'), r.get('run_id'))
            costs[key] = costs.get(key, 0) + (r.get('cost') or 0)
    rows = []
    for m in runs:
        sig = ds_steer.signals(m.get('transcript')) if ds_steer and m.get('transcript') else {}
        steer = {}
        try:
            steer = json.loads((sd / 'runs' / m['run_id'] / 'steer.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        rows.append(dict(m=m, sig=sig, cost=costs.get((m.get('project'), m['run_id'])) or float(m.get('cost_usd') or 0),
                         nudges=[n['key'] for n in steer.get('nudges', [])],
                         has_report=Path(m.get('report') or '').is_file()))
    return rows


def claude_line(helpers):
    done = [m for m in helpers if m.get('state') == 'completed']
    tokens = sum(m.get('tokens_in') or 0 for m in done)
    return 'Claude subagents: %d run(s), %d finished, %.1fM tokens read%s.' % (
        len(helpers), len(done), tokens / 1e6,
        ', longest %s (%s turns)' % (max(done, key=lambda m: m.get('turns') or 0)['run_id'],
                                     max(m.get('turns') or 0 for m in done)) if done else '')


def report(project, since):
    """The full report and the short one, from one pass over the runs."""
    sd = Path(state_dir(project))
    runs = runs_since(sd, since)
    # Claude subagents are recorded beside the workers (provider "claude"); they cost plan usage, not dollars.
    helpers = [m for m in runs if m.get('provider') == 'claude']
    runs = [m for m in runs if m.get('provider') != 'claude']
    rows = analyse(sd, runs)
    states = collections.Counter(r['m']['state'] for r in rows)
    total = sum(r['cost'] for r in rows)
    head = '%d worker run(s) since %s, about $%.2f: %s.' % (
        len(rows), since.strftime('%a %H:%M'), total, ', '.join('%d %s' % (v, k) for k, v in states.most_common()) or 'none')
    attention = []
    for r in rows:
        m = r['m']
        if m['state'] in ('failed', 'timed_out', 'canceled'):
            attention.append('%s %s: %s%s' % (m['run_id'], m['state'], (m.get('error') or '')[:200],
                                               '' if r['has_report'] else ' - NO REPORT'))
        elif m['state'] == 'working' and not (sd / ('%s.json' % m.get('task_id'))).is_file():
            attention.append('%s still marked working with no launcher: it died; the next launch closes it' % m['run_id'])
    long_runs = sorted((r for r in rows if r['sig'].get('steps', 0) >= LONG_STEPS), key=lambda r: -r['sig']['steps'])
    slept = sorted((r for r in rows if r['sig'].get('slept', 0) >= SLEEP_WORTH), key=lambda r: -r['sig']['slept'])
    refused = collections.Counter()
    for r in rows:
        for head_word, n in (r['sig'].get('refused') or {}).items():
            refused[head_word] += n
    nudged = [r for r in rows if r['nudges']]
    try:
        audit_lines = ds_audit.status_lines(project)
        audits_due = len(ds_audit.due(project))
        audits_high = sum(1 for r in ds_audit.open_findings(project) if r.get('severity') == 'high')
    except Exception as exc:   # a broken audit state must not take the report down (review-049)
        audit_lines, audits_due, audits_high = ['audits: could not be read (%s)' % exc], 0, 0
    memory = ds_memory.status_lines(project) + audit_lines
    spend_line = None
    if ds_spend:
        d = ds_spend.spend_dir()
        lim = ds_spend.limits(d)
        parts = []
        for period in ds_spend.PERIODS:
            if lim.get(period):
                parts.append('%s $%.2f of $%.2f' % (ds_spend.label(period), ds_spend.spent(d, period), lim[period]))
        pace = ds_spend.pace(d, 'research')
        if parts:
            spend_line = 'Spend: %s%s.' % ('; '.join(parts), ', ahead of pace (easing off)' if pace['ease'] else ', on pace')
        b = ds_spend.last_balance(d)
        if b:
            spend_line = ((spend_line + ' ') if spend_line else '') + ds_spend.balance_line(d, b['usd'], at=b['at'])
        held, waited = ds_spend.holds(d, since.astimezone(dt.timezone.utc))
        if held or waited:
            spend_line = (spend_line or 'Spend:') + ' Held by the limits: %d launch(es) refused%s, %d made to wait.' % (
                len(held), ' (%s)' % ', '.join('%s %s' % (r['at'][11:16], r.get('kind')) for r in held[:6]) if held else '',
                len(waited))

    lines = []
    if rows:
        lines = ['DeepSeek morning report: ' + head]
        if attention:
            lines.append('Needs attention: ' + '; '.join(attention[:4]) + ('; ...' if len(attention) > 4 else ''))
        if long_runs:
            lines.append('%d long run(s) (100+ steps, $%.2f): %s.' % (len(long_runs), sum(r['cost'] for r in long_runs),
                         ', '.join('%s %d' % (r['m']['run_id'], r['sig']['steps']) for r in long_runs[:4])))
        if slept:
            lines.append('Workers slept %d min waiting on builds.' % (sum(r['sig']['slept'] for r in slept) // 60))
        if spend_line:
            lines.append(spend_line)
    if helpers:
        lines.append(claude_line(helpers))
    if audits_due or audits_high:
        lines.append(audit_lines[0][0].upper() + audit_lines[0][1:] + ('. `python "%s" due` briefs them.' % Path(ds_audit.__file__).resolve()
                                                                      if audits_due else '. `ds_audit.py findings` lists them.'))
    todo = ds_memory.due(project)
    if todo:
        lines.append('Project memory: %s due. Before other worker launches, run `python "%s" due` and start the command(s) it '
                     'prints in the background.' % (' and '.join(todo), Path(ds_memory.__file__).resolve()))
    short = '\n'.join(lines)

    out = ['# DeepSeek morning report: %s' % project.name, '', head, '']
    if helpers:
        out += [claude_line(helpers), '']
    if spend_line:
        out += [spend_line, '']
    if ds_claude:   # the short form leaves this to the SessionStart hook, which adds it in every session
        out += [' '.join(ds_claude.lines(ds_claude.spend_dir())), '']
    out += ['## Needs attention', ''] + (['- ' + a for a in attention] or ['- nothing failed, timed out or got stuck']) + ['']
    out += ['## Long runs (%d+ steps)' % LONG_STEPS, '']
    out += ['- %s: %d steps, context %dk, $%.2f%s' % (r['m']['run_id'], r['sig']['steps'], r['sig']['context'] // 1000, r['cost'],
                                                     ' (nudged: %s)' % ', '.join(r['nudges']) if r['nudges'] else '')
            for r in long_runs] or ['- none']
    out += ['', '## Time spent sleeping', '']
    out += ['- %s: %d min' % (r['m']['run_id'], r['sig']['slept'] // 60) for r in slept] or ['- none worth noting']
    out += ['', '## Refused commands', '']
    out += ['- "%s": %d' % (k, v) for k, v in refused.most_common(8)] or ['- none']
    out += ['', '## Nudges sent', '']
    out += ['- %s: %s' % (r['m']['run_id'], ', '.join(r['nudges'])) for r in nudged] or ['- none']
    out += ['', '## Costliest runs', '']
    out += ['- %s (%s): $%.2f, %s steps' % (r['m']['run_id'], r['m']['state'], r['cost'], r['sig'].get('steps', '?'))
            for r in sorted(rows, key=lambda r: -r['cost'])[:5]] or ['- none']
    out += ['', '## Project memory', ''] + ['- ' + x for x in memory]
    return '\n'.join(out) + '\n', short


def last_report(sd):
    try:
        return local(json.loads((sd / 'reports' / 'morning.json').read_text(encoding='utf-8'))['at'])
    except (OSError, ValueError, KeyError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--project', default='.')
    ap.add_argument('--since', help='ISO time (default: the last report, else 24 hours ago)')
    ap.add_argument('--short', action='store_true')
    ap.add_argument('--no-save', action='store_true')
    a = ap.parse_args(argv)
    project = Path(a.project).resolve()
    sd = Path(state_dir(project))
    now = dt.datetime.now().astimezone()
    since = local(a.since) if a.since else (last_report(sd) or now - dt.timedelta(hours=24))
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    full, short = report(project, since)
    text = short if a.short else full
    saved = None
    if not a.no_save and text:
        rd = sd / 'reports'
        rd.mkdir(parents=True, exist_ok=True)
        saved = rd / ('morning-%s.md' % now.strftime('%Y-%m-%d-%H%M'))
        saved.write_text(full, encoding='utf-8')
        (rd / 'morning.json').write_text(json.dumps({'at': now.isoformat(timespec='seconds')}), encoding='utf-8')
    if text:
        print(text + ('\nFull report: %s' % saved if a.short and saved else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
