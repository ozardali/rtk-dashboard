#!/usr/bin/env python3
"""Local, dependency-free, read-only RTK statistics dashboard."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from codex_usage import default_codex_home, model_usage
from claude_usage import default_claude_home, model_usage as claude_model_usage
from imported_usage import model_usage as imported_model_usage
from functools import lru_cache
from projects import project_root

ROOT = Path(__file__).resolve().parent


def default_database():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'rtk/history.db'


@contextmanager
def database(path):
    # WAL readers may need to create shared-memory files. If the directory is
    # read-only, replay a stable copy in a private temporary directory instead.
    conn = None
    with tempfile.TemporaryDirectory(prefix='rtk-dashboard-') as directory:
        try:
            conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
            conn.execute('SELECT count(*) FROM sqlite_master').fetchone()
        except sqlite3.OperationalError:
            if conn:
                conn.close()
            for attempt in range(3):
                files = [path, Path(str(path) + '-wal')]
                def fingerprint():
                    return [(p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in files]
                before = fingerprint()
                for p in files:
                    target = Path(directory) / p.name
                    target.unlink(missing_ok=True)
                    if p.exists():
                        shutil.copyfile(p, target)
                if before == fingerprint():
                    break
            else:
                raise RuntimeError('The database is busy. Please try again shortly.')
            conn = sqlite3.connect(Path(directory) / path.name)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA query_only=ON')
            yield conn
        finally:
            conn.close()


def statistics(path, days=30, project=''):
    if not path.is_file():
        raise RuntimeError('RTK database not found. Run commands with RTK or use --db.')
    with database(path) as db:
        root = lru_cache(maxsize=4096)(project_root)
        db.create_function('project_root', 1, root)
        columns = {row['name'] for row in db.execute('PRAGMA table_info(commands)')}
        required = {'timestamp', 'rtk_cmd', 'input_tokens', 'output_tokens', 'saved_tokens'}
        if not required <= columns:
            raise RuntimeError('Unsupported RTK commands schema.')
        where, params = ['1=1'], []
        if days:
            where.append("datetime(timestamp) >= datetime('now', ?)")
            params.append(f'-{days} days')
        if project:
            if 'project_path' not in columns:
                raise RuntimeError('This RTK version does not record project paths.')
            where.append('project_root(project_path) = ?')
            params.append(root(project) or project)
        clause = ' AND '.join(where)
        totals = dict(db.execute(f'''SELECT count(*) AS commands,
            coalesce(sum(input_tokens),0) AS input, coalesce(sum(output_tokens),0) AS output,
            coalesce(sum(saved_tokens),0) AS saved,
            coalesce(sum(max(saved_tokens,0)),0) AS gross_saved,
            coalesce(-sum(min(saved_tokens,0)),0) AS expansion,
            min(timestamp) AS first_record, max(timestamp) AS last_record
            FROM commands WHERE {clause}''', params).fetchone())
        totals['percent'] = round(totals['saved'] / totals['input'] * 100, 1) if totals['input'] else 0
        daily = [dict(r) for r in db.execute(f'SELECT date(timestamp) AS day, sum(input_tokens) AS input, sum(output_tokens) AS output, sum(saved_tokens) AS saved, count(*) AS commands FROM commands WHERE {clause} GROUP BY day ORDER BY day', params)]
        # Only the RTK command family is exposed; command arguments can contain secrets.
        command = "CASE WHEN trim(rtk_cmd) LIKE 'rtk %' THEN ltrim(substr(trim(rtk_cmd),5)) ELSE trim(rtk_cmd) END"
        family = f"CASE WHEN instr(({command}), ' ') > 0 THEN substr(({command}),1,instr(({command}),' ')-1) ELSE ({command}) END"
        groups = [dict(r) for r in db.execute(f'SELECT {family} AS name, count(*) AS commands, sum(input_tokens) AS input, sum(saved_tokens) AS saved FROM commands WHERE {clause} GROUP BY name ORDER BY saved DESC LIMIT 20', params)]
        recent = [dict(r) for r in db.execute(f'SELECT timestamp, {family} AS name, input_tokens AS input, output_tokens AS output, saved_tokens AS saved FROM commands WHERE {clause} ORDER BY timestamp DESC, rowid DESC LIMIT 50', params)]
        projects = sorted({root(r[0]) for r in db.execute("SELECT DISTINCT project_path FROM commands")} - {''}) if 'project_path' in columns else []
        return dict(totals=totals, daily=daily, groups=groups, recent=recent, projects=projects, updated=datetime.now(timezone.utc).isoformat())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get('Host', '')
        if host not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
            return self.reply(403, b'Forbidden', 'text/plain')
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{host}'}:
            return self.reply(403, b'Forbidden', 'text/plain')
        url = urlsplit(self.path)
        if url.path == '/api/data':
            try:
                query = parse_qs(url.query)
                days = int(query.get('days', ['30'])[0])
                if days not in {0, 7, 30, 90}:
                    raise ValueError()
                data = statistics(self.server.db_path, days, query.get('project', [''])[0])
                data['model_usage'] = model_usage(getattr(self.server, 'codex_home', default_codex_home()), days, query.get('project', [''])[0])
                usage = data['model_usage']
                claude = claude_model_usage(getattr(self.server, 'claude_home', default_claude_home()), days, query.get('project', [''])[0])
                for row in usage['rows']:
                    row['source'] = 'Codex CLI'
                    row.setdefault('cache_write', 0)
                for row in claude['rows']:
                    row['source'] = 'Claude Code'
                imported = imported_model_usage(getattr(self.server, 'usage_dir', None), days, query.get('project', [''])[0])
                usage['sources'] = [{'name': 'Codex CLI', 'available': usage['available']}, {'name': 'Claude Code', 'available': claude['available']}] + imported['sources']
                usage['rows'] = sorted(usage['rows'] + claude['rows'] + imported['rows'], key=lambda r: r['input'] + r['output'], reverse=True)
                usage['available'] = usage['available'] or claude['available'] or imported['available']
                usage['unreadable_files'] += claude['unreadable_files'] + imported['unreadable_files']
                usage['projects'] = sorted(set(usage['projects']) | set(claude['projects']) | set(imported['projects']))
                usage['totals'] = {key: sum(row[key] for row in usage['rows']) for key in ('input', 'cached', 'cache_write', 'output')}
                data['projects'] = sorted(set(data['projects']) | set(data['model_usage'].pop('projects')))
                return self.reply(200, json.dumps(data).encode(), 'application/json')
            except ValueError:
                return self.reply(400, b'{"error":"Invalid filter"}', 'application/json')
            except (sqlite3.Error, OSError, RuntimeError):
                return self.reply(503, json.dumps({'error': 'Unable to read local usage data. Check the database path and file permissions.'}).encode(), 'application/json')
        assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if url.path not in assets:
            return self.reply(404, b'Not found', 'text/plain')
        name, mime = assets[url.path]
        self.reply(200, (ROOT / 'static' / name).read_bytes(), mime)

    def reply(self, status, body, mime):
        self.send_response(status)
        for key, value in {'Content-Type': mime + '; charset=utf-8', 'Content-Length': str(len(body)), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=default_database())
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--codex-home', type=Path, default=default_codex_home())
    parser.add_argument('--claude-home', type=Path, default=default_claude_home())
    parser.add_argument('--usage-dir', type=Path, help='Directory with exported usage JSONL files from other tools')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.db_path = args.db.expanduser()
    server.codex_home = args.codex_home.expanduser()
    server.claude_home = args.claude_home.expanduser()
    server.usage_dir = args.usage_dir.expanduser() if args.usage_dir else None
    print(f'RTK Dashboard: http://localhost:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
