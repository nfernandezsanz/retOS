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
SseRequester = Callable[
    [str, Mapping[str, str], str | None, float],
    tuple[int, str, dict[str, str]],
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
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc


def default_sse_requester(
    url: str,
    headers: Mapping[str, str],
    last_event_id: str | None,
    timeout: float,
) -> tuple[int, str, dict[str, str]]:
    request_headers = {"Accept": "text/event-stream", **dict(headers)}
    if last_event_id:
        request_headers["Last-Event-ID"] = last_event_id
    request = Request(url, headers=request_headers, method="GET")
    try:
        with urlopen(  # noqa: S310 - local operator-requested smoke URLs.
            request, timeout=timeout
        ) as response:
            event = read_sse_event(response, timeout=timeout)
            content_type = response.headers.get("content-type", "")
            return response.status, content_type, event
    except HTTPError as exc:
        return exc.code, exc.headers.get("content-type", ""), {}
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc


def read_sse_event(response: Any, *, timeout: float) -> dict[str, str]:
    event: dict[str, str] = {}
    max_lines = 80
    for _ in range(max_lines):
        line = response.readline()
        if line == b"":
            break
        text = line.decode("utf-8", errors="replace").strip()
        if text == "":
            if event:
                break
            continue
        if ":" not in text:
            continue
        field, value = text.split(":", 1)
        value = value.lstrip()
        if field == "data" and field in event:
            event[field] = f"{event[field]}\n{value}"
        elif field in {"id", "event", "data"}:
            event[field] = value
        if event.get("event") and event.get("data") and event.get("id"):
            break
    if not event:
        raise RuntimeError(f"progress stream did not emit an event within {timeout:g}s")
    return event


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


def decode_json_list(
    name: str, body: str
) -> tuple[list[Any] | None, SmokeCheck | None]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, fail(name, f"invalid JSON: {exc}")
    if not isinstance(parsed, list):
        return None, fail(name, "expected JSON array")
    return parsed, None


def hashed_event_count(events: list[Any]) -> int:
    return sum(
        1
        for event in events
        if isinstance(event, dict) and isinstance(event.get("event_hash"), str)
    )


def validate_audit_export(export: dict[str, Any]) -> str | None:
    integrity = export.get("integrity")
    if not isinstance(integrity, dict):
        return "missing integrity object"
    event_count = integrity.get("event_count")
    if not isinstance(event_count, int) or event_count <= 0:
        return "missing audit export events"
    if integrity.get("valid") is not True:
        return "audit export integrity is not valid"
    failures = integrity.get("failures")
    if isinstance(failures, list) and failures:
        return f"{len(failures)} audit hash failure(s)"
    return None


def audit_export_detail(export: dict[str, Any]) -> str:
    integrity = export["integrity"]
    event_count = integrity["event_count"]
    continuity_gaps = integrity.get("continuity_gaps")
    gap_count = len(continuity_gaps) if isinstance(continuity_gaps, list) else 0
    suffix = f", {gap_count} limited-window gap(s)" if gap_count else ""
    return f"{event_count} event(s), valid{suffix}"


def validate_sse_event(event: dict[str, str]) -> str | None:
    event_id = event.get("id", "")
    if not event_id.startswith(("progress:", "live:")):
        return f"unexpected event id: {event_id or 'missing'}"
    if not event.get("event"):
        return "missing event name"
    data = event.get("data")
    if not data:
        return "missing event data"
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        return f"invalid event data JSON: {exc}"
    if not isinstance(payload, dict):
        return "event data is not a JSON object"
    if payload.get("id") != event_id:
        return "event data id does not match stream id"
    if payload.get("event") != event.get("event"):
        return "event data name does not match stream event"
    return None


def run_local_smoke(
    *,
    api_url: str,
    web_url: str,
    email: str,
    password: str,
    query: str,
    timeout: float,
    requester: HttpRequester = default_requester,
    sse_requester: SseRequester = default_sse_requester,
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

        for name, path in (
            ("audit journals", "/audit/journal-events?limit=20"),
            ("audit progress", "/audit/progress-events?limit=20"),
        ):
            try:
                audit_status, audit_body = requester(
                    "GET",
                    urljoin(api_url, path),
                    headers,
                    None,
                    timeout,
                )
            except RuntimeError as exc:
                checks.append(fail(name, str(exc)))
                continue
            error = require_success(name, audit_status, audit_body)
            if error:
                checks.append(error)
                continue
            events, json_error = decode_json_list(name, audit_body)
            if json_error:
                checks.append(json_error)
                continue
            hashed_count = hashed_event_count(events or [])
            if events and hashed_count > 0:
                checks.append(ok(name, f"{hashed_count}/{len(events)} hashed event(s)"))
            else:
                checks.append(fail(name, "no hash-chain events returned"))

        try:
            export_status, export_body = requester(
                "GET",
                urljoin(api_url, "/audit/export?limit=40"),
                headers,
                None,
                timeout,
            )
        except RuntimeError as exc:
            checks.append(fail("audit export", str(exc)))
        else:
            error = require_success("audit export", export_status, export_body)
            if error:
                checks.append(error)
            else:
                export, json_error = decode_json("audit export", export_body)
                if json_error:
                    checks.append(json_error)
                else:
                    export_error = validate_audit_export(export)
                    if export_error:
                        checks.append(fail("audit export", export_error))
                    else:
                        checks.append(ok("audit export", audit_export_detail(export)))

        try:
            stream_status, content_type, event = sse_requester(
                urljoin(api_url, "/events/progress"),
                headers,
                None,
                timeout,
            )
        except RuntimeError as exc:
            checks.append(fail("sse progress", str(exc)))
        else:
            if not 200 <= stream_status < 300:
                checks.append(fail("sse progress", f"HTTP {stream_status}"))
            elif not content_type.startswith("text/event-stream"):
                checks.append(
                    fail(
                        "sse progress",
                        f"unexpected content-type: {content_type or 'missing'}",
                    )
                )
            else:
                stream_error = validate_sse_event(event)
                if stream_error:
                    checks.append(fail("sse progress", stream_error))
                else:
                    replay_id = event["id"]
                    try:
                        resumed_status, resumed_content_type, resumed_event = (
                            sse_requester(
                                urljoin(api_url, "/events/progress"),
                                headers,
                                replay_id,
                                timeout,
                            )
                        )
                    except RuntimeError as exc:
                        checks.append(fail("sse progress", f"resume failed: {exc}"))
                    else:
                        if not 200 <= resumed_status < 300:
                            checks.append(
                                fail("sse progress", f"resume HTTP {resumed_status}")
                            )
                        elif not resumed_content_type.startswith("text/event-stream"):
                            checks.append(
                                fail(
                                    "sse progress",
                                    "resume unexpected content-type: "
                                    f"{resumed_content_type or 'missing'}",
                                )
                            )
                        else:
                            resumed_error = validate_sse_event(resumed_event)
                            if resumed_error:
                                checks.append(
                                    fail("sse progress", f"resume {resumed_error}")
                                )
                            else:
                                checks.append(
                                    ok(
                                        "sse progress",
                                        f"{replay_id} -> {resumed_event['id']}",
                                    )
                                )

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
