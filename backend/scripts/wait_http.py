from __future__ import annotations

import sys
import time
import urllib.parse

import httpx


def main() -> None:
    url = sys.argv[1]
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in {"http", "https"}:
        raise SystemExit(f"Unsupported URL scheme for readiness check: {parsed_url.scheme}")

    timeout_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2)
            if 200 <= response.status_code < 500:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.25)

    raise SystemExit(f"Timed out waiting for {url}: {last_error}")


if __name__ == "__main__":
    main()
