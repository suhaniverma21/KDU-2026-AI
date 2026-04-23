import time

import requests


def call_with_retry(fn, max_retries=3):
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code

            if status_code == 429:
                if attempt == max_retries:
                    raise
                time.sleep(2**attempt)
                continue

            if status_code < 500:
                raise

            if attempt == max_retries:
                raise
            time.sleep(2**attempt)
        except requests.ConnectionError:
            if attempt == max_retries:
                raise
            time.sleep(1)
        except requests.Timeout:
            if attempt == max_retries:
                raise
            time.sleep(2**attempt)
