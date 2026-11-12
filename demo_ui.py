"""Local demo of saved, real evaluation traces. No API calls or API keys.

Run: python -X utf8 demo_ui.py --open
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parent
REPORTS = {
    'after': ('Sau cải tiến', 'eval_after.json'),
    'before': ('Trước cải tiến', 'eval_before.json'),
    'bonus': ('Bonus', 'eval_bonus.json'),
}


def read_report(key):
    return json.loads((ROOT / REPORTS[key][1]).read_text(encoding='utf-8-sig'))


class DemoHandler(BaseHTTPRequestHandler):
    def send_data(self, status, content, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, value):
        self.send_data(status, json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        request = urlparse(self.path)
        try:
            if request.path == '/':
                self.send_data(200, (ROOT / 'demo' / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            elif request.path == '/api/reports':
                reports = []
                for key, (label, filename) in REPORTS.items():
                    data = read_report(key)
                    reports.append({
                        'key': key, 'label': label, 'file': filename,
                        'summary': data['summary'], 'config': data['config'],
                        'cases': [{'id': case['id'], 'question': case['question'],
                                   'score': case['grade'].get('score')} for case in data['cases']],
                    })
                self.send_json(200, reports)
            elif request.path == '/api/case':
                query = parse_qs(request.query)
                key = query.get('report', ['after'])[0]
                case_id = query.get('case', ['H1'])[0]
                if key not in REPORTS:
                    self.send_json(400, {'error': 'Bộ kết quả không hợp lệ.'})
                    return
                data = read_report(key)
                case = next((case for case in data['cases'] if case['id'] == case_id), None)
                if case is None:
                    self.send_json(404, {'error': 'Không tìm thấy case trong bộ kết quả.'})
                    return
                self.send_json(200, {key: case[key] for key in ('id', 'question', 'scenario', 'result', 'grade')})
            else:
                self.send_json(404, {'error': 'Không tìm thấy đường dẫn.'})
        except (OSError, ValueError, KeyError):
            self.send_json(500, {'error': 'Không đọc được báo cáo. Kiểm tra các file eval JSON trong repo.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Mở trình duyệt khi khởi động')
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), DemoHandler)
    except OSError as error:
        parser.exit(1, f'Không mở được cổng {args.port}: {error}. Thử --port 8766.\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Demo: {url}\nĐọc kết quả đã lưu, không gọi API. Nhấn Ctrl+C để dừng.', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
