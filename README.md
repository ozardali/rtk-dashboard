# RTK Dashboard

A small local dashboard for **Rust Token Killer (RTK)**. See how many command output tokens you save, compare models, and filter usage by project.

Built with Python and plain JavaScript. No packages to install, no cloud account, and no tracking.

## Quick start

You need Python 3.10 or newer and an RTK history database. Run some commands through [RTK](https://github.com/rtk-ai/rtk) first.

```bash
python3 server.py
```

Open **http://localhost:8765**. Press Ctrl+C to stop the server.

```bash
python3 server.py --port 8766
python3 server.py --db /path/to/history.db
python3 server.py --codex-home /path/to/.codex
python3 server.py --claude-home /path/to/.claude
python3 server.py --usage-dir /path/to/usage-exports
```

The default database is `$XDG_DATA_HOME/rtk/history.db`, or `~/.local/share/rtk/history.db` when that variable is not set. Missing data shows an error. The app does not create demo data.

## What you can see

- Net tokens saved, output reduction, and command counts.
- Daily output before and after RTK.
- Savings by command family and the last 50 commands.
- Model input, output, cache reads, and cache writes by tool.
- Filters for the last 7, 30, or 90 days, or all time.
- Project filters that group nested folders and Git worktrees.
- Automatic updates every 30 seconds.
- An optional savings estimate using a token price you enter.

## Tool support

RTK command savings work with any tool that writes commands to the same RTK database. The database does not tell this dashboard which tool ran each command.

Model usage has two built-in readers:

| Tool | Local source |
| --- | --- |
| Codex CLI | `$CODEX_HOME/sessions`, or `~/.codex/sessions` |
| Claude Code | `$CLAUDE_CONFIG_DIR/projects`, or `~/.claude/projects`, including subagent files |
| Other tools | JSONL exports loaded with `--usage-dir` |

Other tools need an export in the format below. Their native session files are not read automatically.

### Add usage from another tool

Create a folder outside this repository. Add one or more `.jsonl` files with one JSON object per completed request:

```json
{"id":"request-001","tool":"My coding tool","model":"example-model","timestamp":"2026-10-21T10:00:00Z","cwd":"/path/to/project","input":1200,"cached":400,"cache_write":0,"output":250}
```

Then start the dashboard with `python3 server.py --usage-dir /path/to/usage-exports`.

`id`, `tool`, `model`, and `timestamp` are required. Use a stable request ID that is unique within each tool. Repeated IDs for the same tool are counted once, with the first valid record kept. `cwd` is optional and enables project filtering. Counts are non-negative integers and default to zero. Invalid records are skipped. Use UTC timestamps with a `Z` suffix or include a time zone offset. Timestamps without an offset are treated as UTC.

`input` must include cache reads and writes. `cached` and `cache_write` are parts of that total. Their sum cannot exceed `input`. Export per-request counts, not cumulative session totals. Avoid importing requests already covered by the built-in readers, because separate sources are added together.

Only usage fields are returned to the browser. There is no need to include prompts, responses, or API keys in an export.

## How to read the numbers

RTK tokens are estimates of command output size. Net savings subtract output expansion from gross savings. They do not measure your full model usage or your actual bill.

Model usage is separate from RTK savings. Total tokens means input plus output. Cache reads and writes are already part of input, so do not add them again. Reused context can count on every request. These numbers do not show subscription limits or billing totals.

Codex usage comes from changes in cumulative counters. Repeated counters and copied sessions with the same ID are counted once. Claude Code usage comes from assistant records. Repeated request and message IDs use the largest reported counters. Only local records are included, so deleted, archived, or remote sessions may be missing.

## Privacy and local access

The server listens on `127.0.0.1`. It checks Host and Origin headers and uses a content security policy. Keep it local. It has no user login system.

The RTK database is opened for reading only. If SQLite cannot read its WAL files in place, the app reads a temporary copy. Command arguments, raw output, and conversation text are not sent to the browser. Project paths are sent to your local browser for filtering.

## Development

```bash
python3 -m unittest -v
node --check static/app.js
```

Node is only needed for the optional JavaScript syntax check. The app itself does not need Node.
