import json
from pathlib import Path
import tempfile
import unittest
from imported_usage import model_usage


class ImportedUsageTests(unittest.TestCase):
    def test_duplicates_filters_validation_and_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            record = dict(id='one', tool='Example tool', model='example-model',
                          timestamp='2026-01-01T00:00:00Z', cwd='/project-a',
                          input=100, cached=25, cache_write=10, output=20,
                          prompt='PRIVATE CONTENT')
            records = [record, record, dict(record, id='bad', cached=101),
                       dict(record, id='negative', output=-1),
                       dict(record, id='two', tool='Another tool', cwd='/project-b')]
            (folder / 'usage.jsonl').write_text('\n'.join(json.dumps(r) for r in records) + '\ninvalid\n')
            result = model_usage(folder, 0)
            self.assertEqual(len(result['rows']), 2)
            self.assertEqual(sum(r['input'] for r in result['rows']), 200)
            self.assertNotIn('PRIVATE CONTENT', json.dumps(result))
            self.assertEqual(len(model_usage(folder, 0, '/project-a')['rows']), 1)
            self.assertEqual(model_usage(folder, 7)['rows'], [])
            self.assertEqual(len(result['sources']), 2)

    def test_optional_and_missing_directory(self):
        self.assertFalse(model_usage(None)['available'])
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(model_usage(Path(directory) / 'missing')['available'])
            self.assertEqual(model_usage(Path(directory), 0)['rows'], [])


if __name__ == '__main__':
    unittest.main()
