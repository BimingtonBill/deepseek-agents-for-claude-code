"""Where DeepSeek tokens go, from the worker transcripts on disk. Local only: it costs nothing to run.

    python tools/ds_cost.py <project folder> [<project folder> ...]

Prints the token split (cache reads, fresh input, output), spend by kind and effort, and the costliest
runs. Prices are DeepSeek list rates, assumed; the shares are what matter. See docs/design/cost.md.
"""
import collections
import json
import os
import sys
from pathlib import Path

projects = sys.argv[1:]
rows = []
for proj in projects:
    runs = Path(proj) / 'local' / 'agents' / 'runs'
    if not runs.is_dir():
        continue
    for rd in runs.iterdir():
        mf = rd / 'manifest.json'
        if not mf.is_file():
            continue
        try:
            m = json.loads(mf.read_text(encoding='utf-8-sig'))
        except ValueError:
            continue
        t = m.get('transcript')
        if not t or not os.path.exists(t):
            continue
        files = [Path(t)]
        sub = Path(t).with_suffix('') / 'subagents'
        if sub.is_dir():
            files += list(sub.glob('*.jsonl'))
        seen, u = set(), collections.Counter(fresh_in=0, cache_read=0, cache_write=0, out=0)
        calls = 0
        for f in files:
            for line in open(f, encoding='utf-8', errors='replace'):
                if '"usage"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                msg = e.get('message') or {}
                us, mid = msg.get('usage'), msg.get('id')
                if not us or mid in seen:
                    continue
                seen.add(mid)
                calls += 1
                u['fresh_in'] += us.get('input_tokens') or 0
                u['cache_read'] += us.get('cache_read_input_tokens') or 0
                u['cache_write'] += us.get('cache_creation_input_tokens') or 0
                u['out'] += us.get('output_tokens') or 0
        rows.append(dict(project=Path(proj).name, run=rd.name, kind=m.get('kind'), effort=m.get('effort'),
                         calls=calls, **u))

# DeepSeek list prices per million tokens (assumed; relative sizes are what matter):
# cache hit 0.028, cache miss 0.28, output 0.42.
PRICE = dict(cache_read=0.028, fresh_in=0.28, cache_write=0.28, out=0.42)
def cost(r):
    return sum(r.get(k, 0) * p for k, p in PRICE.items()) / 1e6

tot = collections.Counter()
for r in rows:
    for k in PRICE:
        tot[k] += r.get(k, 0)
total_cost = sum(tot[k] * p for k, p in PRICE.items()) / 1e6
if not rows or not total_cost:
    print('no worker runs with usage found under %s (runs live in <project>/local/agents/runs, or the state '
          'dir the launcher chose)' % (', '.join(projects) or 'the folders given'))
    sys.exit(0)
print('runs with transcripts: %d, API calls: %d' % (len(rows), sum(r['calls'] for r in rows)))
print('tokens (M): cache-read %.1f | fresh-in %.1f | cache-write %.1f | out %.1f' % tuple(tot[k] / 1e6 for k in ('cache_read', 'fresh_in', 'cache_write', 'out')))
print('share of cost: ' + ', '.join('%s %.0f%%' % (k, 100 * tot[k] * PRICE[k] / 1e6 / total_cost) for k in PRICE) + '  (total ~$%.2f)' % total_cost)

by = collections.defaultdict(lambda: [0, 0.0, 0, 0])
for r in rows:
    b = by[(r['kind'], r['effort'])]
    b[0] += 1; b[1] += cost(r); b[2] += r['out']; b[3] += r['calls']
print('\nkind/effort      runs   cost$  avg-out-k  avg-calls')
for (k, e), (n, c, o, calls) in sorted(by.items(), key=lambda x: -x[1][1])[:10]:
    print('%-10s %-5s %4d  %6.2f  %8.0f  %8.0f' % (k, e, n, c, o / n / 1000, calls / n))

print('\ncostliest runs:')
for r in sorted(rows, key=cost, reverse=True)[:6]:
    print('  $%.3f  %-44s %-8s calls=%-4d out=%dk cache-read=%dk' % (cost(r), r['run'][:44], r['effort'], r['calls'], r['out'] // 1000, r['cache_read'] // 1000))
