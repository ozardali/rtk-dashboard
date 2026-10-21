"""Resolve recorded working directories to project roots, without running Git."""
from pathlib import Path
import os


def project_root(value):
    if not value or not isinstance(value, str) or not Path(value).is_absolute():
        return ''
    path = Path(os.path.normpath(value))
    home = Path.home()
    if path in (Path('/'), home):
        return ''
    parents = (path, *path.parents)
    workspace = next((p for p in parents if p.name in ('Projects', 'projects', 'workspace', 'workspaces')), None)
    # Never let an unrelated repository above the workspace absorb its projects.
    candidates = parents[:parents.index(workspace)] if workspace else parents
    for parent in candidates:
        marker = parent / '.git'
        if marker.is_file():
            try:
                reference = marker.read_text().strip()
                if reference.startswith('gitdir:'):
                    gitdir = Path(reference.split(':', 1)[1].strip())
                    if not gitdir.is_absolute():
                        gitdir = parent / gitdir
                    gitdir = gitdir.resolve()
                    if gitdir.parent.name == 'worktrees' and gitdir.parent.parent.name == '.git':
                        main = gitdir.parent.parent.parent
                        if (main / '.git').is_dir():
                            return str(main)
            except OSError:
                pass
        if marker.exists():
            return str(parent)
    # Historical directories may no longer exist on disk.
    for parent in parents:
        if parent.name in ('Projects', 'projects', 'workspace', 'workspaces'):
            relative = path.relative_to(parent)
            return str(parent / relative.parts[0]) if relative.parts else ''
    markers = ('package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', '.project-root')
    for parent in reversed(parents):
        if parent not in (Path('/'), home) and any((parent / marker).is_file() for marker in markers):
            return str(parent)
    return str(path)
