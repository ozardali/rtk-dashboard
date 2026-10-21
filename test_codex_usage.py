import json
from pathlib import Path
import tempfile
import unittest
from codex_usage import model_usage


class UsageTests(unittest.TestCase):
    def test_models_filters_duplicates_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'sessions').mkdir()
            events = []

            def event(kind, payload, stamp='2099-01-01T00:00:00Z'):
                events.append(dict(type=kind, payload=payload, timestamp=stamp))

            def usage(i, c, o, stamp='2099-01-01T00:00:00Z'):
                event('event_msg', dict(type='token_count', info=dict(total_token_usage=dict(
                    input_tokens=i, cached_input_tokens=c, output_tokens=o))), stamp)

            event('session_meta', dict(id='one', cwd='/a'))
            event('turn_context', dict(model='model-a', cwd='/a'))
            event('response_item', dict(text='SECRET conversation'))
            usage(100, 50, 20, '2000-01-01T00:00:00Z')
            usage(100, 50, 20)
            usage(160, 70, 30)
            event('turn_context', dict(model='model-b', cwd='/b'))
            usage(200, 80, 40)
            usage(10, 0, 2)
            source = '\n'.join(map(json.dumps, events)) + '\n{"partial":'
            (home / 'sessions' / 'one.jsonl').write_text(source)
            (home / 'sessions' / 'copy.jsonl').write_text(source)
            data = model_usage(home, 30)
            self.assertEqual(data['rows'], [dict(name='model-a', input=60, cached=20, cache_write=0, output=10),
                                            dict(name='model-b', input=50, cached=10, cache_write=0, output=12)])
            self.assertNotIn('SECRET', json.dumps(data))
            self.assertEqual(model_usage(home, 0, '/a')['rows'][0]['input'], 160)
            self.assertEqual(model_usage(home, 0, '/missing')['rows'], [])
            self.assertEqual(data['projects'], ['/a', '/b'])

    def test_missing_home(self):
        with tempfile.TemporaryDirectory() as directory:
            result = model_usage(Path(directory))
            self.assertFalse(result['available'])
            self.assertEqual(result['rows'], [])
