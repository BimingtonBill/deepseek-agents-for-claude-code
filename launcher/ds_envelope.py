"""The standard opening of every worker report (and Claude subagent report), so Claude can read a few lines
instead of the whole thing.

On 2026-09-25 the OpenSkyrim sessions pulled about 2.1M characters of worker output into their own context
in 20 hours (reports ran 6-12k characters), 11 of 19 reviews had no verdict line, and fewer than half the
reports said what was left. Every report now opens with:

    Status: done | partial | blocked
    Verdict: accept | fix first | reject                (reviews; research: answered | partly | not found)
    Summary: up to five lines, the outcome first
    Left: what was not done, or "nothing"
    Next: follow-up tasks worth briefing, or "none"

then a blank line and the details. The launcher prints only this opening and the report's path, keeps the
full report on disk, and records the fields in the run's manifest.

    python ds_envelope.py note --kind review          the instruction the worker gets
    python ds_envelope.py head --report <file> [--json]   the opening, or exit 1 when there is none
"""
import argparse
import json
import re
import sys
from pathlib import Path

VERDICTS = {
    'review': ('accept', 'fix first', 'reject'),
    'critic': ('accept', 'fix first', 'reject'),
    'research': ('answered', 'partly', 'not found'),
    'websearch': ('answered', 'partly', 'not found'),
    'analysis': ('answered', 'partly', 'not found'),
}
FIELDS = ('status', 'verdict', 'summary', 'left', 'next')
FIELD = re.compile(r'^\s*(?:[-*>]\s*)?(?:\*\*|__)?(status|verdict|summary|left|next)(?:\*\*|__)?\s*:\s*(?:\*\*|__)?\s*(.*)$', re.I)


def note(kind):
    """The instruction, on one line (it goes into the worker's system prompt, which is one argument)."""
    verdict = VERDICTS.get(kind)
    fields = ['"Status: done | partial | blocked"'] + (['"Verdict: %s"' % ' | '.join(verdict)] if verdict else []) + [
        '"Summary: ..." (up to five lines, the outcome or answer first)', '"Left: ..." (what you did not do or '
        'could not finish, or nothing)', '"Next: ..." (follow-up tasks worth briefing, or none)']
    return ('Start your report with these lines, each on its own line, before anything else (no preamble such as '
            '"I have what I need"): %s. Then a blank line and the details the brief asks for. Claude reads only '
            'those opening lines unless it needs the details, so they must stand on their own.' % ', '.join(fields))


def status_word(text):
    """done, partial or blocked, by meaning rather than the first word: review-060 (2026-09-25) pointed out that
    "task incomplete - blocked on transport" came out as "task". Anything else is kept, lowercased."""
    words = set(re.findall(r'[a-z]+', text.lower()))
    if words & {'blocked', 'stuck'}:
        return 'blocked'
    if words & {'partial', 'partly', 'incomplete', 'unfinished'}:
        return 'partial'
    if words & {'done', 'complete', 'completed', 'finished'}:
        return 'done'
    return text.strip().lower()[:40]


def parse(text):
    """The opening block of a report: dict(fields..., head=<the block's text>), or None when it has none.
    The block may come after a short preamble or a heading, and fields may be bold or list items."""
    lines = re.sub(r'^\s*<!--.*?-->\s*', '', text or '', flags=re.S).splitlines()
    # The whole block on one line, "Status: done | Verdict: ... | Summary: ..." (seen 2026-09-26):
    # split it before each field name, only on a line that starts with Status.
    lines = [part for line in lines for part in (
        re.split(r'\s*\|\s*(?=(?:\*\*)?(?:Verdict|Summary|Left|Next)\b(?:\*\*)?\s*:)', line)
        if FIELD.match(line) and FIELD.match(line).group(1).lower() == 'status' else [line])]
    start = next((i for i, l in enumerate(lines[:40]) if FIELD.match(l) and FIELD.match(l).group(1).lower() == 'status'), None)
    if start is None:
        return None
    out, block, current = {}, [], None
    for line in lines[start:start + 40]:
        m = FIELD.match(line)
        if m:
            current = m.group(1).lower()
            if current in out:          # a second Status: the block is over
                break
            out[current] = m.group(2).strip().rstrip('*_').strip()
            block.append(line.rstrip())
        elif line.lstrip().startswith('#'):
            break                       # the details begin
        elif not line.strip():
            if 'summary' in out:
                break                   # the blank line after the block
        elif current:                   # a continuation line of the current field
            out[current] = (out[current] + '\n' + line.strip()).strip()
            block.append(line.rstrip())
    if 'summary' not in out:
        return None
    out['status'] = status_word(out.get('status', ''))
    if out.get('verdict'):
        v = out['verdict'].lower()
        out['verdict'] = next((x for vs in VERDICTS.values() for x in vs if v.startswith(x)), v.split('.')[0][:40])
    out['head'] = '\n'.join(block).strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('note'); n.add_argument('--kind', default='')
    h = sub.add_parser('head'); h.add_argument('--report', required=True); h.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if a.cmd == 'note':
        print(note(a.kind))
        return 0
    try:
        text = Path(a.report).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return 1
    env = parse(text)
    if not env:
        return 1
    print(json.dumps(dict(env, chars=len(text))) if a.json else env['head'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
