import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from server import Handler, statistics

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'history.db'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE commands(timestamp TEXT, rtk_cmd TEXT, input_tokens INTEGER, output_tokens INTEGER, saved_tokens INTEGER, project_path TEXT)')
            db.executemany("INSERT INTO commands VALUES(datetime('now'), ?, ?, ?, ?, ?)", [('rtk git status SECRET',100,25,75,'/project-a'),('rtk git diff',900,450,450,'/project-b'),('ls',0,0,0,'/project-a')])
    def tearDown(self):
        self.tmp.cleanup()
    def test_aggregation_and_privacy(self):
        before = self.path.read_bytes()
        d = statistics(self.path, 0)
        self.assertEqual(d['totals']['saved'],525)
        self.assertEqual(d['totals']['percent'],52.5)
        self.assertEqual(d['groups'][0]['name'],'git')
        self.assertNotIn('SECRET',json.dumps(d))
        self.assertEqual(statistics(self.path,0,'/project-a')['totals']['saved'],75)
        self.assertEqual(statistics(self.path,0,"' OR 1=1 --")['totals']['commands'],0)
        self.assertEqual(before,self.path.read_bytes())
    def test_empty_and_missing(self):
        self.assertEqual(statistics(self.path,0,'missing')['totals']['percent'],0)
        with self.assertRaises(RuntimeError): statistics(Path(self.tmp.name)/'absent')
    def test_net_savings_and_expansion(self):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO commands VALUES(datetime('now'), 'rtk ls', 10, 26, -16, '/project-a')")
        totals = statistics(self.path, 0)['totals']
        self.assertEqual(totals['gross_saved'], 525)
        self.assertEqual(totals['expansion'], 16)
        self.assertEqual(totals['saved'], 509)
        self.assertEqual(totals['saved'], totals['input'] - totals['output'])
        self.assertIsNotNone(totals['last_record'])
    def test_project_root_includes_nested_working_directories(self):
        root = Path(self.tmp.name) / 'Projects' / 'demo'
        (root / '.git').mkdir(parents=True)
        with sqlite3.connect(self.path) as db:
            db.executemany("INSERT INTO commands VALUES(datetime('now'), 'rtk ls', 100, 25, 75, ?)",
                           [(str(root),), (str(root / 'client' / 'src'),)])
        result = statistics(self.path, 0, str(root))
        self.assertEqual(result['totals']['commands'], 2)
        self.assertEqual(result['totals']['saved'], 150)
        self.assertIn(str(root), result['projects'])
        self.assertNotIn(str(root / 'client' / 'src'), result['projects'])
    def test_http_guards(self):
        from email.message import Message
        from io import BytesIO
        from types import SimpleNamespace
        def request(path, headers=None):
            handler = Handler.__new__(Handler)
            handler.path = path
            handler.headers = Message()
            handler.headers['Host'] = '127.0.0.1:8765'
            for key, value in (headers or {}).items():
                if key in handler.headers: del handler.headers[key]
                handler.headers[key] = value
            handler.server = SimpleNamespace(server_port=8765,db_path=self.path,
                                             codex_home=Path(self.tmp.name), claude_home=Path(self.tmp.name))
            handler.request_version = 'HTTP/1.1'
            handler.requestline = 'GET ' + path + ' HTTP/1.1'
            handler.command = 'GET'
            handler.wfile = BytesIO()
            handler.do_GET()
            return handler.wfile.getvalue()
        response = request('/api/data?days=0')
        self.assertIn(b'200 OK',response)
        self.assertIn(b"frame-ancestors 'none'",response)
        self.assertEqual(json.loads(response.split(b'\r\n\r\n')[1])['totals']['commands'],3)
        usage = json.loads(response.split(b'\r\n\r\n')[1])['model_usage']
        self.assertEqual([s['name'] for s in usage['sources']], ['Codex CLI', 'Claude Code'])
        self.assertEqual(usage['rows'], [])
        self.assertIn(b'200 OK',request('/'))
        for path,headers,status in [('/api/data?days=999',{},400),('/server.py',{},404),('/api/data',{'Host':'evil.example'},403),('/api/data',{'Origin':'https://evil.example'},403)]:
            self.assertIn(str(status).encode(),request(path,headers).split(b'\r\n')[0])

if __name__ == '__main__': unittest.main()
