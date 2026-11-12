"""Chay eval goc voi khoang nghi chung cho agent va judge.

Dung cung tham so nhu evals/run_evals.py. Mac dinh cach moi lan goi AI
it nhat 6 giay (khoang 10 yeu cau/phut), phu hop gioi han 15 RPM.
Loi may chu 500/502/503/504 hoac timeout duoc thu lai toi da 2 lan.
"""
from email.utils import parsedate_to_datetime
from pathlib import Path
import sys
from threading import Lock
import time
import urllib.error

from providers import Provider


class CallPacer:
    def __init__(self, interval=6.0, clock=time.monotonic, sleeper=time.sleep):
        self.interval = interval
        self.clock = clock
        self.sleeper = sleeper
        self.next_allowed = 0.0
        self.lock = Lock()

    def wait(self):
        with self.lock:
            delay = self.next_allowed - self.clock()
            if delay > 0:
                print(f'Cho {delay:.1f} giay de tranh vuot gioi han API...', flush=True)
                self.sleeper(delay)
            self.next_allowed = self.clock() + self.interval


def retry_delay(http_error, attempt):
    delay = 6.0 * (2 ** attempt)
    headers = getattr(http_error, 'headers', None)
    retry_after = headers.get('Retry-After') if headers else None
    if retry_after:
        try:
            requested = float(retry_after)
        except ValueError:
            try:
                requested = parsedate_to_datetime(retry_after).timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                return None
        delay = max(delay, requested)
    # Neu may chu yeu cau cho lau, dung de nguoi dung kiem tra.
    return delay if delay <= 60 else None


def paced_complete(original_complete, pacer, max_retries=2, sleeper=time.sleep):
    def complete(provider, messages, schemas):
        for attempt in range(max_retries + 1):
            pacer.wait()
            try:
                return original_complete(provider, messages, schemas)
            except Exception as error:
                http_error = error.__cause__ or error
                status = getattr(http_error, 'code', None)
                timed_out = (
                    isinstance(error, TimeoutError)
                    or isinstance(http_error, TimeoutError)
                    or (
                        isinstance(http_error, urllib.error.URLError)
                        and isinstance(http_error.reason, TimeoutError)
                    )
                )
                if (status not in (500, 502, 503, 504) and not timed_out) or attempt >= max_retries:
                    raise
                delay = retry_delay(http_error, attempt)
                if delay is None:
                    raise
                label = f'HTTP {status}' if status is not None else 'Timeout'
                print(
                    f'{label}: cho {delay:.1f} giay, '
                    f'thu lai {attempt + 1}/{max_retries}...',
                    flush=True
                )
                sleeper(delay)
    return complete


def main():
    pacer = CallPacer()
    original_complete = Provider.complete
    Provider.complete = paced_complete(original_complete, pacer)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / 'evals'))
        import run_evals
        return run_evals.main()
    finally:
        Provider.complete = original_complete


if __name__ == '__main__':
    sys.exit(main())
