"""Read aggregate usage only; never expose conversation contents."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
from projects import project_root


def default_codex_home():
    return Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))


def model_usage(home, days=30, project=''):
    root = lru_cache(maxsize=4096)(project_root)
    selected = (root(project) or project) if project else ''
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    groups, projects, seen_sessions = {}, set(), set()
    errors = 0
    fields = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens')
    for path in sorted((home / 'sessions').rglob('*.jsonl')):
        model, cwd, previous = 'Unknown', '', dict.fromkeys(fields, 0)
        try:
            with path.open(encoding='utf-8') as source:
                for line in source:
                    try:
                        event = json.loads(line)
                        payload = event.get('payload')
                        if not isinstance(payload, dict):
                            continue
                        kind = event.get('type')
                        if kind == 'session_meta':
                            session_id = payload.get('id')
                            if session_id and session_id in seen_sessions:
                                break
                            if session_id:
                                seen_sessions.add(session_id)
                            cwd = payload.get('cwd') or ''
                        elif kind == 'turn_context':
                            model = payload.get('model') or 'Unknown'
                            cwd = payload.get('cwd') or cwd
                        if root(cwd):
                            projects.add(root(cwd))
                        if kind != 'event_msg' or payload.get('type') != 'token_count':
                            continue
                        info = payload.get('info')
                        usage = info.get('total_token_usage') if isinstance(info, dict) else None
                        if not isinstance(usage, dict):
                            continue
                        current = {k: usage.get(k, 0) for k in fields}
                        if any(type(v) is not int or v < 0 for v in current.values()):
                            continue
                        stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        # Cumulative counters can repeat in status events. Advance
                        # the baseline even for events excluded by the filters.
                        reset = any(current[k] < previous[k] for k in ('input_tokens', 'output_tokens'))
                        delta = {k: max(0, current[k] - (0 if reset else previous[k])) for k in fields}
                        previous = current
                        if (cutoff and stamp < cutoff) or (selected and root(cwd) != selected):
                            continue
                        if not any(delta.values()):
                            continue
                        row = groups.setdefault(model, dict(name=model, input=0, cached=0, cache_write=0, output=0))
                        for target, key in zip(('input', 'cached', 'cache_write', 'output'), fields):
                            row[target] += delta[key]
                    except (ValueError, TypeError, KeyError, AttributeError):
                        # An active writer may leave an incomplete last line.
                        continue
        except OSError:
            errors += 1
    return dict(rows=sorted(groups.values(), key=lambda r: r['input'] + r['output'], reverse=True),
                projects=sorted(projects), unreadable_files=errors,
                available=(home / 'sessions').is_dir())
