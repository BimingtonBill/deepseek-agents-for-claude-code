"""DeepSeek spend limits, per day and per week, the way Claude's usage limits work: a worker does not
start when the limit is used up or when what it usually costs would not fit, and a running worker is
stopped when the limit is reached. The limit resets at local midnight (day) or Monday midnight (week;
set --from-now counts only spending from that moment and starts each week on that weekday).

Spending is also paced, so the limit is rarely reached at all. The budget is spread evenly over the day
or week, plus a head start of 20% of the limit. While spending stays within that pace, nothing changes.
When it runs ahead, workers ease off in steps (see EASE):
  1. lower effort (max becomes high), a note to finish in few steps, delegation one level down;
  2. effort low, and one worker at a time (a new one waits for others to finish, up to 20 minutes);
  3. as 2, and no coders or leads until spending is back on pace.

    python ds_spend.py status                  what has been spent, what is left, when it resets
    python ds_spend.py set 2 --per day         limit DeepSeek spend to $2 a day (--per week for a week,
                                               --from-now to ignore what was spent before now)
    python ds_spend.py off [--per day|week]    remove a limit (both when --per is left out)
    python ds_spend.py backfill <project> ...  add past runs from those projects to the spend record

ds-agent.ps1 calls the rest itself: check (before a worker starts), live (every 15 seconds while it
runs) and record (when it ends). Everything lives in one folder shared by every project, so a limit
covers all of them: DS_SPEND_DIR, else ~/.claude-deepseek/spend. It holds limits.json, spend.jsonl (one
line per finished run) and live/ (what each running worker has spent so far).

Costs are worked out from the token counts in each worker's transcript at DeepSeek's list prices
(PRICE below; override with "prices" in limits.json). They come out higher than the DeepSeek dashboard
(roughly a third higher in the one comparison made, 2026-09-24), so limits act a little early; the
dashboard is the real bill. Nothing here calls DeepSeek: the launcher already
fetches the balance and passes it in.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

# DeepSeek list prices, US dollars per million tokens.
PRICE = dict(cache_read=0.028, fresh_in=0.28, cache_write=0.28, out=0.42)

# What a run of each kind cost on average over 233 runs in two projects (2026-09, tools/ds_cost.py),
# used until the spend record holds a few runs of that kind.
DEFAULT_ESTIMATE = dict(impl=0.70, lead=0.60, analysis=0.40, research=0.25, digest=0.25, review=0.15,
                        critic=0.15, advisor=0.15, websearch=0.05, selftest=0.02, probe=0.02)
FALLBACK_ESTIMATE = 0.30
PERIODS = ('day', 'week')
WARN_AT = 0.8          # say so once a limit is this far used
REFUSED = 3            # exit code for "over the limit"

# Pacing. The share of a limit that is "on pace" at a moment is the share of the window gone by, plus
# HEAD_START of the limit (so the first job of the day isn't held back). EASE_AT are the ratios of
# (spent + this worker's estimate) to that allowance where each easing step begins.
HEAD_START = 0.2
EASE_AT = (1.0, 1.25, 1.5)
EXPENSIVE = ('impl', 'lead')
EASE = {1: 'lower effort, short jobs, delegation one level down',
        2: 'effort low, one worker at a time, delegation one level down',
        3: 'effort low, one worker at a time, no coders or leads, delegation one level down'}


def spend_dir():
    return Path(os.environ.get('DS_SPEND_DIR') or Path.home() / '.claude-deepseek' / 'spend')


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def limits(d):
    return read_json(d / 'limits.json', {})


def prices(d):
    p = dict(PRICE)
    p.update(limits(d).get('prices') or {})
    return p


# --- Costs from a transcript ---

def usage(transcript, since=None):
    """Token totals in a worker transcript (and its in-process subagents' transcripts), once per API
    message, counting only messages at or after `since` (a resumed run's earlier launches are already
    recorded)."""
    u = dict(cache_read=0, fresh_in=0, cache_write=0, out=0)
    if not transcript or not os.path.exists(transcript):
        return u
    files = [Path(transcript)]
    sub = Path(transcript).with_suffix('') / 'subagents'
    if sub.is_dir():
        files += sorted(sub.glob('*.jsonl'))
    seen = set()
    for f in files:
        with open(f, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                msg = e.get('message') or {}
                us, mid = msg.get('usage'), msg.get('id')
                if not isinstance(us, dict) or (mid and mid in seen):
                    continue
                if since and e.get('timestamp') and parse_time(e['timestamp']) < since:
                    continue
                if mid:
                    seen.add(mid)
                u['fresh_in'] += us.get('input_tokens') or 0
                u['cache_read'] += us.get('cache_read_input_tokens') or 0
                u['cache_write'] += us.get('cache_creation_input_tokens') or 0
                u['out'] += us.get('output_tokens') or 0
    return u


def cost(u, price=PRICE):
    return sum(u.get(k, 0) * p for k, p in price.items()) / 1e6


def parse_time(text):
    """An ISO time as an aware UTC datetime; one without a zone is taken as local time."""
    t = dt.datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    return (t if t.tzinfo else t.astimezone()).astimezone(dt.timezone.utc)


# --- Windows ---

def window(period, now=None, d=None):
    """Start and end of the current day or week, in local time. A week runs Monday to Monday, or from
    the weekday in limits.json "weekStartsOn" (0 Monday .. 6 Sunday). A window that "countFrom" falls
    inside starts there instead, so spending before a limit was set with --from-now is not counted and
    the pace spreads the budget over what is left of that window."""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'week':
        first = int(limits(d).get('weekStartsOn') or 0) if d else 0
        start -= dt.timedelta(days=(start.weekday() - first) % 7)
        end = start + dt.timedelta(days=7)
    else:
        end = start + dt.timedelta(days=1)
    # Rebuild from the date so a daylight-saving change doesn't shift midnight by an hour.
    start = dt.datetime(start.year, start.month, start.day).astimezone()
    end = dt.datetime(end.year, end.month, end.day).astimezone()
    since = limits(d).get('countFrom') if d else None
    if since:
        since = parse_time(since).astimezone()
        if start < since < end:
            start = since
    return start, end


def ledger(d):
    rows = []
    try:
        with open(d / 'spend.jsonl', encoding='utf-8') as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def pid_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def live(d, exclude=None):
    """What running workers have spent so far. A file whose launcher is gone is a leftover (the run
    was recorded, or killed before it could be): drop it."""
    out = {}
    folder = d / 'live'
    if not folder.is_dir():
        return out
    for f in folder.glob('*.json'):
        r = read_json(f, None)
        if not r or r.get('run_id') == exclude:
            continue
        if not pid_alive(r.get('pid')):
            try:
                f.unlink()
            except OSError:
                pass
            continue
        out[r['run_id']] = r
    return out


def spent(d, period, now=None, exclude=None):
    """Recorded runs that ended in this window plus what running workers have spent."""
    start, _ = window(period, now, d)
    done = sum(r.get('cost') or 0 for r in ledger(d) if r.get('ended') and parse_time(r['ended']) >= start)
    running = sum(r.get('cost') or 0 for r in live(d, exclude).values())
    return done + running


def estimate(d, kind):
    """What a run of this kind usually costs: the mean of its last 20 recorded runs once there are 3,
    else the default table."""
    # Newest by end time, not file order: a backfill appends whole projects one after another.
    rows = sorted((r for r in ledger(d) if r.get('kind') == kind and r.get('cost') and r.get('ended')),
                  key=lambda r: parse_time(r['ended']))
    costs = [r['cost'] for r in rows][-20:]
    if len(costs) >= 3:
        return sum(costs) / len(costs)
    return DEFAULT_ESTIMATE.get(kind, FALLBACK_ESTIMATE)


def resets(period, now=None, d=None):
    now = (now or dt.datetime.now().astimezone()).astimezone()
    _, end = window(period, now, d)
    left = end - now
    h, m = divmod(int(left.total_seconds()) // 60, 60)
    when = end.strftime('%H:%M') if period == 'day' else end.strftime('%a %H:%M')
    return '%s (in %s)' % (when, ('%dd %dh' % (h // 24, h % 24)) if h >= 24 else '%dh %dm' % (h, m))


def label(period):
    return 'today' if period == 'day' else 'this week'


# --- Commands ---

def check(d, kind, balance=None, now=None):
    """(ok, lines) for starting a worker of this kind now."""
    lim = limits(d)
    est = estimate(d, kind)
    lines = []
    for period in PERIODS:
        cap = lim.get(period)
        if not cap:
            continue
        used = spent(d, period, now)
        left = cap - used
        if left <= 0:
            return False, ['DeepSeek spend limit reached: $%.2f of $%.2f %s. It resets at %s. Do this work '
                           'yourself, or ask the user to raise the limit (python ds_spend.py set <dollars> '
                           '--per %s).' % (used, cap, label(period), resets(period, now, d), period)]
        if est > left:
            return False, ['A %s worker usually costs about $%.2f, and only $%.2f of the $%.2f %s limit is '
                           'left (resets at %s). Do this work yourself, give it to a cheaper kind, or ask the '
                           'user to raise the limit.' % (kind, est, left, cap, 'daily' if period == 'day' else
                                                         'weekly', resets(period, now, d))]
        if (used + est) / cap >= WARN_AT:
            lines.append('%d%% of the %s DeepSeek limit will be used once this worker is done ($%.2f + about '
                         '$%.2f of $%.2f); it resets at %s.' % (100 * (used + est) / cap, 'daily' if period ==
                         'day' else 'weekly', used, est, cap, resets(period, now, d)))
    if balance is not None and est > balance:
        return False, ['Your DeepSeek balance is $%.2f and a %s worker usually costs about $%.2f. Ask the user '
                       'to top up at platform.deepseek.com, or do this work yourself.' % (balance, kind, est)]
    return True, lines


def pace(d, kind, now=None):
    """How far spending is ahead of an even pace: ease 0 (on pace) to 3, the period behind it, and when a
    worker of this kind fits the pace again (None when only the reset will do)."""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    lim = limits(d)
    est = estimate(d, kind)
    best = dict(ease=0, period=None, fits_at=None)
    for period in PERIODS:
        cap = lim.get(period)
        if not cap:
            continue
        start, end = window(period, now, d)
        gone = (now - start) / (end - start)
        need = spent(d, period, now) + est
        ratio = need / (cap * min(1.0, gone + HEAD_START))
        ease = sum(ratio > t for t in EASE_AT)
        if ease > best['ease']:
            fits = start + (end - start) * max(0.0, need / cap - HEAD_START)
            best = dict(ease=ease, period=period, fits_at=fits if fits < end else None)
    return best


def plan(d, kind, balance=None, now=None, lineage='', waited=False):
    """Whether and how a worker of this kind starts now: the hard limits (check), then the pace. Returns
    ok, lines (what to tell Claude), ease, effort_cap ('high', 'low' or None) and wait (other workers are
    running and this one should wait for them)."""
    ok, lines = check(d, kind, balance, now)
    out = dict(ok=ok, lines=lines, ease=0, effort_cap=None, wait=False)
    if not ok:
        return out
    p = pace(d, kind, now)
    ease = out['ease'] = p['ease']
    if not ease:
        return out
    ahead = 'DeepSeek spending is ahead of an even pace for the %s limit' % ('daily' if p['period'] == 'day' else 'weekly')
    if ease >= 3 and kind in EXPENSIVE:
        when = ('it fits the pace again at %s' % p['fits_at'].astimezone().strftime('%H:%M' if p['period'] == 'day' else '%a %H:%M')
                if p['fits_at'] else 'it fits again after the reset at %s' % resets(p['period'], now, d))
        out.update(ok=False, lines=['%s, so %s workers wait (%s). Do this yourself, split off the parts a research or '
                                    'review worker can do, or wait.' % (ahead, kind, when)])
        return out
    out['effort_cap'] = 'high' if ease == 1 else 'low'
    mine = set(filter(None, lineage.split('/')))
    others = [r for r in live(d).values() if r.get('run_id') not in mine]
    out['wait'] = ease >= 2 and bool(others) and not waited
    lines.append('%s: easing off (%s).' % (ahead, EASE[ease]))
    return out


def lowered(level, d, now=None):
    """The delegation level to work at: one lower while spending runs ahead of pace (never below 1)."""
    return max(1, level - 1) if pace(d, 'research', now)['ease'] else level


class locked:
    """Hold spend_dir/pace.lock, so workers starting at the same moment (a lead's spawn_workers) take
    turns to check the pace and claim their place, instead of all seeing no one running."""
    def __init__(self, d):
        self.lock = d / 'pace.lock'
        self.fd = None

    def __enter__(self):
        import time
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(150):
            try:
                self.fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.lock.stat().st_mtime > 30:   # left by a killed process
                        self.lock.unlink()
                except OSError:
                    pass
                time.sleep(0.1)
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            try:
                self.lock.unlink()
            except OSError:
                pass


def over(d, run_id, now=None):
    """The first limit that running workers and recorded runs together have now reached, or None."""
    lim = limits(d)
    for period in PERIODS:
        cap = lim.get(period)
        if cap and spent(d, period, now) >= cap:
            return period, cap
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--dir', help='the spend folder (default: DS_SPEND_DIR or ~/.claude-deepseek/spend)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('status'); s.add_argument('--balance', type=float)
    s = sub.add_parser('set'); s.add_argument('dollars', type=float); s.add_argument('--per', choices=PERIODS, default='day')
    s.add_argument('--from-now', action='store_true', help='count only spending from now on; with --per week, weeks '
                   'also start on today\'s weekday instead of Monday')
    s = sub.add_parser('off'); s.add_argument('--per', choices=PERIODS)
    s = sub.add_parser('check'); s.add_argument('--kind', required=True); s.add_argument('--balance', type=float)
    s.add_argument('--json', action='store_true', help='print the plan (pace included) as JSON')
    s.add_argument('--run-id'); s.add_argument('--pid', type=int)
    s.add_argument('--lineage', default='', help="the worker's lineage (claude/<parent>/...): its ancestors never make it wait")
    s.add_argument('--claim', action='store_true', help='when it may start, mark it running (needs --run-id and --pid)')
    s.add_argument('--waited', action='store_true', help='it has waited long enough; start even if others run')
    for name in ('live', 'record'):
        s = sub.add_parser(name)
        s.add_argument('--run-id', required=True); s.add_argument('--transcript', required=True)
        s.add_argument('--since', required=True, help='when this launch started (ISO time)')
        s.add_argument('--pid', type=int, help='the launcher process')
        s.add_argument('--kind'); s.add_argument('--effort'); s.add_argument('--project')
    s = sub.add_parser('backfill'); s.add_argument('projects', nargs='+')
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else spend_dir()

    if a.cmd == 'set':
        if a.dollars <= 0:
            ap.error('a limit must be more than 0; use "off" to remove one')
        d.mkdir(parents=True, exist_ok=True)
        lim = limits(d); lim[a.per] = round(a.dollars, 2)
        if a.from_now:
            lim['countFrom'] = dt.datetime.now().astimezone().isoformat(timespec='seconds')
            if a.per == 'week':
                lim['weekStartsOn'] = dt.date.today().weekday()
        (d / 'limits.json').write_text(json.dumps(lim, indent=2) + '\n', encoding='utf-8')
        print('DeepSeek spend is now limited to $%.2f a %s, across all projects%s.' % (
            a.dollars, a.per, ', counting from now' + (' (weeks start on %s)' % dt.date.today().strftime('%A')
                                                        if a.per == 'week' else '') if a.from_now else ''))
        return 0
    if a.cmd == 'off':
        lim = limits(d)
        for period in ([a.per] if a.per else PERIODS):
            lim.pop(period, None)
        if d.is_dir():
            (d / 'limits.json').write_text(json.dumps(lim, indent=2) + '\n', encoding='utf-8')
        print('Limits now: %s' % (', '.join('$%.2f a %s' % (lim[p], p) for p in PERIODS if lim.get(p)) or 'none'))
        return 0
    if a.cmd == 'status':
        lim = limits(d)
        for period in PERIODS:
            used = spent(d, period)
            cap = lim.get(period)
            if cap:
                pct = min(used / cap, 1)
                bar = '#' * round(20 * pct) + '-' * (20 - round(20 * pct))
                print('%-9s [%s] %3d%%  $%.2f of $%.2f, resets %s' % (label(period), bar, 100 * used / cap, used, cap, resets(period, None, d)))
            else:
                print('%-9s $%.2f spent, no limit' % (label(period), used))
        p = pace(d, 'research')
        if any(lim.get(x) for x in PERIODS):
            print('pace:     %s' % ('ahead of an even pace, easing off: ' + EASE[p['ease']] if p['ease'] else 'on pace'))
        running = live(d)
        if running:
            print('running:  %d worker(s), $%.2f so far' % (len(running), sum(r.get('cost') or 0 for r in running.values())))
        if a.balance is not None:
            print('balance:  $%.2f' % a.balance)
        print('(estimated from transcripts at list prices; the DeepSeek dashboard has the real bill)')
        return 0
    if a.cmd == 'check':
        if not a.json:
            ok, lines = check(d, a.kind, a.balance)
            for line in lines:
                print(line)
            return 0 if ok else REFUSED
        with locked(d):
            out = plan(d, a.kind, a.balance, lineage=a.lineage, waited=a.waited)
            if out['ok'] and not out['wait'] and a.claim and a.run_id and a.pid:
                (d / 'live').mkdir(parents=True, exist_ok=True)
                (d / 'live' / ('%s.json' % a.run_id)).write_text(
                    json.dumps(dict(run_id=a.run_id, pid=a.pid, cost=0, kind=a.kind)), encoding='utf-8')
        print(json.dumps(out))
        return 0 if out['ok'] else REFUSED
    if a.cmd in ('live', 'record'):
        u = usage(a.transcript, parse_time(a.since))
        c = cost(u, prices(d))
        (d / 'live').mkdir(parents=True, exist_ok=True)
        lf = d / 'live' / ('%s.json' % a.run_id)
        if a.cmd == 'live':
            lf.write_text(json.dumps(dict(run_id=a.run_id, pid=a.pid, cost=c, kind=a.kind)), encoding='utf-8')
            hit = over(d, a.run_id)
            if hit:
                print('the %s DeepSeek spend limit ($%.2f) is used up; it resets at %s' % ('daily' if hit[0] == 'day' else 'weekly', hit[1], resets(hit[0], None, d)))
                return REFUSED
            return 0
        row = dict(run_id=a.run_id, kind=a.kind, effort=a.effort, project=a.project, started=a.since,
                   ended=dt.datetime.now().astimezone().isoformat(timespec='seconds'), cost=round(c, 5), **u)
        with open(d / 'spend.jsonl', 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(row) + '\n')
        try:
            lf.unlink()
        except OSError:
            pass
        print('$%.3f' % c)
        return 0
    if a.cmd == 'backfill':
        d.mkdir(parents=True, exist_ok=True)
        have = {r.get('run_id') for r in ledger(d)}
        added, total = 0, 0.0
        with open(d / 'spend.jsonl', 'a', encoding='utf-8') as fh:
            for proj in a.projects:
                runs = Path(proj) / 'local' / 'agents' / 'runs'
                for mf in sorted(runs.glob('*/manifest.json')) if runs.is_dir() else []:
                    m = read_json(mf, {})
                    if not m.get('run_id') or m['run_id'] in have or not m.get('ended') or not m.get('transcript'):
                        continue
                    u = usage(m['transcript'])
                    c = cost(u, prices(d))
                    if not c:
                        continue
                    fh.write(json.dumps(dict(run_id=m['run_id'], kind=m.get('kind'), effort=m.get('effort'),
                                             project=m.get('project'), started=m.get('started'), ended=m['ended'],
                                             cost=round(c, 5), backfilled=True, **u)) + '\n')
                    have.add(m['run_id']); added += 1; total += c
        print('added %d past run(s), $%.2f' % (added, total))
        return 0


if __name__ == '__main__':
    sys.exit(main())
