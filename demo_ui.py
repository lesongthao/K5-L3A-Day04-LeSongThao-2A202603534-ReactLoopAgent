"""Local question/answer demo and replay of saved evaluation traces.

Run: python -X utf8 demo_ui.py --open
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse
import webbrowser
from agent import run_agent
from bonus.tools import BonusTools
from providers import CONFIG, Provider
from run_evals_slow import CallPacer, paced_complete

ROOT = Path(__file__).resolve().parent
REPORTS = {
    'after': ('Sau cải tiến', 'eval_after.json'),
    'before': ('Trước cải tiến', 'eval_before.json'),
    'bonus': ('Bonus', 'eval_bonus.json'),
}
RUN_LOCK = Lock()
PACER = CallPacer()


class InteractiveProvider(Provider):
    def __init__(self, key, emit):
        self.name, self.model = 'gemini', 'gemini-3.1-flash-lite'
        self.url, self.key = CONFIG['gemini'][1], key
        self.emit = emit
        self.step = 0

    def complete(self, messages, schemas):
        self.step += 1
        self.emit({'event': 'thinking', 'step': self.step, 'message': 'AI đang xử lý câu hỏi và bằng chứng…'})
        response = paced_complete(Provider.complete, PACER)(self, messages, schemas)
        self.emit({'event': 'model', 'step': self.step, 'finish': response['finish']})
        return response


class InteractiveTools(BonusTools):
    def __init__(self, mode, emit, provider):
        super().__init__(mode=mode)
        self.emit, self.provider = emit, provider

    def execute(self, name, arguments):
        self.emit({'event': 'tool_started', 'step': self.provider.step, 'name': name, 'arguments': arguments})
        result = super().execute(name, arguments)
        self.emit({'event': 'tool', 'step': self.provider.step, 'name': name, 'arguments': arguments, 'result': result})
        return result


def read_report(key):
    return json.loads((ROOT / REPORTS[key][1]).read_text(encoding='utf-8-sig'))


class DemoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/api/ask':
            self.send_json(404, {'error': 'Không tìm thấy đường dẫn.'})
            return
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            self.send_json(403, {'error': 'Chỉ chấp nhận giao diện cục bộ.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32000:
                raise ValueError()
            body = json.loads(self.rfile.read(size))
            question = body.get('question', '').strip()
            mode = body.get('mode', 'snapshot')
            key = (body.get('key') or os.getenv('GEMINI_API_KEY') or '').strip()
            if not question or len(question) > 6000 or mode not in ('snapshot', 'live') or len(key) > 512:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            self.send_json(400, {'error': 'Nhập câu hỏi từ 1–6000 ký tự và chọn nguồn dữ liệu hợp lệ.'})
            return
        if not key:
            self.send_json(400, {'error': 'Cần Gemini API key: nhập vào ô mật khẩu hoặc khởi động server từ terminal đã đặt GEMINI_API_KEY.'})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self.send_json(409, {'error': 'Agent đang trả lời câu hỏi khác. Đợi lượt hiện tại kết thúc.'})
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True

            def emit(event):
                self.wfile.write((json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8'))
                self.wfile.flush()

            provider = InteractiveProvider(key, emit)
            tools = InteractiveTools(mode, emit, provider)
            result = run_agent(question, provider, tools, max_steps=12)
            emit({'event': 'done', 'result': result})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            RUN_LOCK.release()

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
    print(f'Demo: {url}\nHỏi đáp gọi Gemini thật; phát lại đọc file eval. Nhấn Ctrl+C để dừng.', flush=True)
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
