import json
from pathlib import Path
import tempfile
import unittest
from claude_usage import model_usage


class ClaudeUsageTests(unittest.TestCase):
    def test_accounting_duplicates_streaming_filters_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            folder = home / 'projects' / 'example' / 'subagents'
            folder.mkdir(parents=True)

            def event(ident, output, model='claude-example', cwd='/a', stamp='2099-01-01T00:00:00Z'):
                return dict(type='assistant', cwd=cwd, timestamp=stamp, requestId='req-'+ident,
                            message=dict(id=ident, model=model, content='SECRET', usage=dict(
                                input_tokens=10, cache_read_input_tokens=100,
                                cache_creation_input_tokens=20, output_tokens=output)))

            events = [event('one', 1), event('one', 5), event('two', 7, cwd='/b'),
                      event('old', 3, stamp='2000-01-01T00:00:00Z'),
                      event('synthetic', 99, model='<synthetic>')]
            text = '\n'.join(map(json.dumps, events)) + '\n{"partial"'
            (folder / 'one.jsonl').write_text(text)
            (folder / 'copy.jsonl').write_text(text)
            data = model_usage(home, 30)
            self.assertEqual(data['rows'], [dict(name='claude-example', input=260, cached=200,
                                                cache_write=40, output=12)])
            self.assertNotIn('SECRET', json.dumps(data))
            self.assertEqual(model_usage(home, 30, '/a')['rows'][0]['output'], 5)
            self.assertEqual(model_usage(home, 0)['rows'][0]['output'], 15)
            self.assertEqual(model_usage(home, 0, '/missing')['rows'], [])
            self.assertEqual(data['projects'], ['/a', '/b'])

    def test_missing_home(self):
        with tempfile.TemporaryDirectory() as directory:
            data = model_usage(Path(directory))
            self.assertEqual(data['rows'], [])
            self.assertFalse(data['available'])
