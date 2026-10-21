import json
from pathlib import Path
import tempfile
import unittest
from projects import project_root
from codex_usage import model_usage as codex_usage
from claude_usage import model_usage as claude_usage


class ProjectTests(unittest.TestCase):
    def test_roots_deleted_paths_and_nested_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'Projects' / 'demo'
            (repo / '.git').mkdir(parents=True)
            child = repo / 'client' / 'src'
            self.assertEqual(project_root(str(child)), str(repo))
            nested = repo / 'nested'
            nested.mkdir()
            (nested / '.git').write_text('gitdir: /example/worktrees/nested')
            self.assertEqual(project_root(str(nested / 'src')), str(nested))
            self.assertEqual(project_root(str(repo.parent / 'deleted' / 'src')), str(repo.parent / 'deleted'))
            self.assertEqual(project_root(str(repo.parent)), '')

    def test_both_readers_group_and_filter_subdirectories(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            repo = home / 'Projects' / 'demo'
            (repo / '.git').mkdir(parents=True)
            codex_events, claude_events = [], []
            for index, cwd in enumerate((repo, repo / 'client' / 'src')):
                stamp = '2099-01-01T00:00:00Z'
                codex_events.extend([
                    dict(type='turn_context', payload=dict(cwd=str(cwd), model='example')),
                    dict(type='event_msg', timestamp=stamp, payload=dict(type='token_count', info=dict(
                        total_token_usage=dict(input_tokens=100*(index+1), output_tokens=10*(index+1)))))])
                claude_events.append(dict(type='assistant', timestamp=stamp, cwd=str(cwd),
                                         message=dict(id=str(index), model='example', usage=dict(input_tokens=100, output_tokens=10))))
            for folder, events in [('sessions', codex_events), ('projects', claude_events)]:
                (home / folder).mkdir()
                (home / folder / 'one.jsonl').write_text('\n'.join(map(json.dumps, events)))
            for reader in (codex_usage, claude_usage):
                result = reader(home, 0, str(repo))
                self.assertEqual(result['projects'], [str(repo)])
                self.assertEqual(result['rows'][0]['input'], 200)
                self.assertEqual(reader(home, 0, str(repo / 'client'))['rows'][0]['input'], 200)
