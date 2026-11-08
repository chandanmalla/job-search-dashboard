"""Bounded backoff for HTTP 429/502/503 and transient URL errors. No live calls."""
import urllib.error
import urllib.request

RETRY_CODES = (429, 502, 503)


def _wait_seconds(exc, delay, cap):
    headers = getattr(exc, "headers", None)
    retry_after = headers.get("Retry-After") if headers is not None else None
    if retry_after is not None and str(retry_after).strip().isdigit():
        delay = float(retry_after)
    if delay < 0:
        delay = 0
    return min(cap, delay)


def urlopen_retry(opener, *, max_retries=4, sleep=None, cap=20.0, base=1.0):
    """Call opener() until it returns or retries are exhausted.

    opener performs one attempt. sleep(seconds) defaults to time.sleep.
    The wait for one retry never exceeds cap seconds. max_retries is the
    number of retries after the first attempt.
    """
    import time
    if sleep is None:
        sleep = time.sleep
    delay = base
    for attempt in range(max_retries + 1):
        try:
            return opener()
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_CODES or attempt >= max_retries:
                raise
            wait = _wait_seconds(exc, delay, cap)
            sleep(wait)
            delay = min(cap, delay * 2)
        except urllib.error.URLError:
            if attempt >= max_retries:
                raise
            sleep(min(cap, delay))
            delay = min(cap, delay * 2)


def install_backoff(*, max_retries=4, sleep=None, cap=20.0):
    """Wrap urllib.request.urlopen. Returns the previous function."""
    orig = urllib.request.urlopen

    def wrapped(*args, **kwargs):
        def opener():
            return orig(*args, **kwargs)
        return urlopen_retry(opener, max_retries=max_retries, sleep=sleep, cap=cap)

    urllib.request.urlopen = wrapped
    return orig
