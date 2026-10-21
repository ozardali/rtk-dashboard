"""Read per-request usage exports from any tool, without message contents."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from projects import project_root


def model_usage(directory, days=30, project=''):
    groups, projects, sources, seen = {}, set(), set(), set()
    errors = 0
    available = directory is not None and Path(directory).is_dir()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    selected = (project_root(project) or project) if project else ''
    for path in sorted(Path(directory).rglob('*.jsonl')) if available else []:
        try:
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                        tool, model, ident = (event[k] for k in ('tool', 'model', 'id'))
                        if not all(isinstance(v, str) and v.strip() for v in (tool, model, ident)):
                            continue
                        stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        values = {k: event.get(k, 0) for k in ('input', 'cached', 'cache_write', 'output')}
                        if any(type(v) is not int or v < 0 for v in values.values()):
                            continue
                        if values['cached'] + values['cache_write'] > values['input']:
                            continue
                        cwd = project_root(event.get('cwd', ''))
                        if cwd:
                            projects.add(cwd)
                        sources.add(tool)
                        if (tool, ident) in seen:
                            continue
                        seen.add((tool, ident))
                        if (cutoff and stamp < cutoff) or (selected and cwd != selected):
                            continue
                        row = groups.setdefault((tool, model), dict(source=tool, name=model, input=0, cached=0, cache_write=0, output=0))
                        for key, value in values.items():
                            row[key] += value
                    except (ValueError, TypeError, KeyError, AttributeError):
                        continue
        except (OSError, UnicodeError):
            errors += 1
    return dict(rows=list(groups.values()), projects=sorted(projects),
                sources=[dict(name=tool, available=True) for tool in sorted(sources)],
                unreadable_files=errors, available=available)
