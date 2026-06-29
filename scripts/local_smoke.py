#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

HttpRequester = Callable[
    [str, str, Mapping[str, str], dict[str, Any] | None, float],
    tuple[int, str],
]


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    detail: str


def ok(name: str, detail: str) -> SmokeCheck:
    return SmokeCheck(name=name, status="OK", detail=detail)


def fail(name: str, detail: str) -> SmokeCheck:
    return SmokeCheck(name=name, status="FAIL", detail=detail)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(name: str, *, root: Path = ROOT, default: str = "") -> str:
    if os.environ.get(name):
        return os.environ[name]
    for env_path in (root / ".env", root / ".env.example"):
        value = read_env_file(env_path).get(name)
        if value:
            return value
    return default


def default_requester(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, str]:
    data = None
    request_headers = dict(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(  # noqa: S310 - local operator-requested smoke URLs.
            request, timeout=timeout
        ) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            return response.status, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc


def require_success(name: str, status: int, body: str) -> SmokeCheck | None:
    if 200 <= status < 300:
        return None
    detail = body[:180].strip() or f"HTTP {status}"
    return fail(name, f"HTTP {status}: {detail}")


def decode_json(
    name: str, body: str
) -> tuple[dict[str, Any] | None, SmokeCheck | None]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, fail(name, f"invalid JSON: {exc}")
    if not isinstance(parsed, dict):
        return None, fail(name, "expected JSON object")
    return parsed, None


def run_local_smoke(
    *,
    api_url: str,
    web_url: str,
    email: str,
    password: str,
    query: str,
    timeout: float,
    requester: HttpRequester = default_requester,
) -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []

    try:
        web_status, web_body = requester("GET", web_url, {}, None, timeout)
    except RuntimeError as exc:
        checks.append(fail("console", str(exc)))
    else:
        error = require_success("console", web_status, web_body)
        checks.append(error or ok("console", web_url))

    try:
        ready_status, ready_body = requester(
            "GET", urljoin(api_url, "/readyz"), {}, None, timeout
        )
    except RuntimeError as exc:
        checks.append(fail("api readiness", str(exc)))
    else:
        error = require_success("api readiness", ready_status, ready_body)
        if error:
            checks.append(error)
        else:
            readiness, json_error = decode_json("api readiness", ready_body)
            if json_error:
                checks.append(json_error)
            else:
                components = readiness.get("components", {}) if readiness else {}
                checks.append(
                    ok(
                        "api readiness",
                        f"database={components.get('database', 'unknown')}",
                    )
                )

    try:
        version_status, version_body = requester(
            "GET", urljoin(api_url, "/versionz"), {}, None, timeout
        )
    except RuntimeError as exc:
        checks.append(fail("api version", str(exc)))
    else:
        error = require_success("api version", version_status, version_body)
        checks.append(error or ok("api version", "runtime metadata available"))

    token = ""
    try:
        auth_status, auth_body = requester(
            "POST",
            urljoin(api_url, "/auth/login"),
            {},
            {"email": email, "password": password},
            timeout,
        )
    except RuntimeError as exc:
        checks.append(fail("admin login", str(exc)))
    else:
        error = require_success("admin login", auth_status, auth_body)
        if error:
            checks.append(error)
        else:
            auth, json_error = decode_json("admin login", auth_body)
            if json_error:
                checks.append(json_error)
            else:
                token = str(auth.get("access_token") or "")
                checks.append(
                    ok("admin login", "token issued" if token else "missing token")
                )
                if not token:
                    checks[-1] = fail("admin login", "missing access_token")

    domain_id = ""
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            seed_status, seed_body = requester(
                "POST",
                urljoin(api_url, "/demo/seed"),
                headers,
                {"rebuild_index": True},
                timeout,
            )
        except RuntimeError as exc:
            checks.append(fail("demo seed", str(exc)))
        else:
            error = require_success("demo seed", seed_status, seed_body)
            if error:
                checks.append(error)
            else:
                seed, json_error = decode_json("demo seed", seed_body)
                if json_error:
                    checks.append(json_error)
                else:
                    domain_id = str(seed.get("domain_id") or "")
                    indexed_segments = int(seed.get("indexed_segments") or 0)
                    if domain_id and indexed_segments > 0:
                        checks.append(
                            ok("demo seed", f"{indexed_segments} indexed segments")
                        )
                    else:
                        checks.append(
                            fail("demo seed", "missing domain_id or indexed segments")
                        )

    if token and domain_id:
        headers = {"Authorization": f"Bearer {token}"}
        search_url = urljoin(
            api_url,
            f"/domains/{domain_id}/search?q={quote_plus(query)}&limit=3",
        )
        try:
            search_status, search_body = requester(
                "GET", search_url, headers, None, timeout
            )
        except RuntimeError as exc:
            checks.append(fail("demo search", str(exc)))
        else:
            error = require_success("demo search", search_status, search_body)
            if error:
                checks.append(error)
            else:
                search, json_error = decode_json("demo search", search_body)
                if json_error:
                    checks.append(json_error)
                else:
                    hits = search.get("hits", [])
                    if isinstance(hits, list) and hits:
                        checks.append(
                            ok("demo search", f"{len(hits)} hit(s) for {query!r}")
                        )
                    else:
                        checks.append(fail("demo search", f"no hits for {query!r}"))

    return checks


def render_checks(checks: list[SmokeCheck]) -> str:
    width = max(len(check.name) for check in checks) if checks else 0
    lines = ["RetOS local smoke", "Checks:"]
    for check in checks:
        lines.append(f"[{check.status:<4}] {check.name:<{width}}  {check.detail}")
    failures = sum(check.status == "FAIL" for check in checks)
    lines.append(f"Summary: {failures} failure(s)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise a running local RetOS stack through API and web endpoints."
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--web-url", default="http://localhost:8080")
    parser.add_argument(
        "--email",
        default=env_value("RETOS_BOOTSTRAP_ADMIN_EMAIL", default="admin@retos.dev"),
    )
    parser.add_argument(
        "--password",
        default=env_value(
            "RETOS_BOOTSTRAP_ADMIN_PASSWORD",
            default="retos-dev-admin-change-me",
        ),
    )
    parser.add_argument("--query", default="Apollo guidance")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    checks = run_local_smoke(
        api_url=args.api_url.rstrip("/"),
        web_url=args.web_url,
        email=args.email,
        password=args.password,
        query=args.query,
        timeout=args.timeout,
    )
    print(render_checks(checks))
    return 1 if any(check.status == "FAIL" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
