"""Aggregate Claude Code usage without returning message contents."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
from projects import project_root


def default_claude_home():
    return Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude'))


def model_usage(home, days=30, project=''):
    root = lru_cache(maxsize=4096)(project_root)
    selected = (root(project) or project) if project else ''
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    messages, projects, groups = {}, set(), {}
    errors = 0
    fields = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens')
    for path in sorted((home / 'projects').rglob('*.jsonl')):
        try:
            with path.open(encoding='utf-8') as source:
                for line in source:
                    try:
                        event = json.loads(line)
                        if event.get('type') != 'assistant':
                            continue
                        message = event.get('message', {})
                        usage = message.get('usage')
                        if not isinstance(usage, dict) or message.get('model') == '<synthetic>':
                            continue
                        values = {key: usage.get(key, 0) for key in fields}
                        if any(type(v) is not int or v < 0 for v in values.values()):
                            continue
                        ident = message.get('id') or event.get('uuid')
                        if not ident:
                            continue
                        stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        cwd = event.get('cwd') or ''
                        if root(cwd):
                            projects.add(root(cwd))
                        # Content blocks and copied transcripts can repeat the
                        # same response. Keep its largest reported counters.
                        key = (event.get('requestId'), ident)
                        if key in messages:
                            for field in fields:
                                messages[key]['usage'][field] = max(messages[key]['usage'][field], values[field])
                        else:
                            messages[key] = dict(usage=values, stamp=stamp, cwd=cwd,
                                                 model=message.get('model') or 'Unknown')
                    except (ValueError, TypeError, KeyError, AttributeError):
                        continue
        except OSError:
            errors += 1
    for item in messages.values():
        if (cutoff and item['stamp'] < cutoff) or (selected and root(item['cwd']) != selected):
            continue
        usage = item['usage']
        row = groups.setdefault(item['model'], dict(name=item['model'], input=0, cached=0, cache_write=0, output=0))
        row['input'] += usage['input_tokens'] + usage['cache_read_input_tokens'] + usage['cache_creation_input_tokens']
        row['cached'] += usage['cache_read_input_tokens']
        row['cache_write'] += usage['cache_creation_input_tokens']
        row['output'] += usage['output_tokens']
    return dict(rows=sorted(groups.values(), key=lambda r: r['input'] + r['output'], reverse=True),
                projects=sorted(projects), unreadable_files=errors,
                available=(home / 'projects').is_dir())
