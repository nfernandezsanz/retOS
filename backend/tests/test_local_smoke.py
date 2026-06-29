from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


def load_local_smoke() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "local_smoke.py"
    spec = importlib.util.spec_from_file_location("local_smoke", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load local smoke from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_smoke_exercises_api_and_web_flow() -> None:
    smoke = load_local_smoke()
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def requester(
        method: str,
        url: str,
        _headers: Mapping[str, str],
        payload: dict[str, Any] | None,
        _timeout: float,
    ) -> tuple[int, str]:
        calls.append((method, url, payload))
        if url == "http://web.local":
            return 200, "<html><title>RetOS</title></html>"
        if url == "http://api.local/readyz":
            return 200, json.dumps({"components": {"database": "ok"}})
        if url == "http://api.local/versionz":
            return 200, json.dumps({"version": "local"})
        if url == "http://api.local/auth/login":
            return 200, json.dumps({"access_token": "local-token"})
        if url == "http://api.local/demo/seed":
            return 200, json.dumps({"domain_id": "domain-demo", "indexed_segments": 4})
        if url == "http://api.local/domains/domain-demo/search?q=Apollo+guidance&limit=3":
            return 200, json.dumps({"hits": [{"title": "Apollo Guidance Notes"}]})
        if url == "http://api.local/audit/journal-events?limit=20":
            return 200, json.dumps([{"event_hash": "journal-hash"}])
        if url == "http://api.local/audit/progress-events?limit=20":
            return 200, json.dumps([{"event_hash": "progress-hash"}])
        return 404, "{}"

    checks = smoke.run_local_smoke(
        api_url="http://api.local",
        web_url="http://web.local",
        email="admin@retos.dev",
        password="retos-dev-admin-change-me",  # noqa: S106 - local fixture password.
        query="Apollo guidance",
        timeout=1,
        requester=requester,
    )

    assert {check.name: check.status for check in checks} == {
        "console": "OK",
        "api readiness": "OK",
        "api version": "OK",
        "admin login": "OK",
        "demo seed": "OK",
        "demo search": "OK",
        "audit journals": "OK",
        "audit progress": "OK",
    }
    assert calls[-3][1].endswith("/domains/domain-demo/search?q=Apollo+guidance&limit=3")
    assert calls[-2][1].endswith("/audit/journal-events?limit=20")
    assert calls[-1][1].endswith("/audit/progress-events?limit=20")


def test_local_smoke_stops_mutating_calls_when_login_fails() -> None:
    smoke = load_local_smoke()
    calls: list[str] = []

    def requester(
        _method: str,
        url: str,
        _headers: Mapping[str, str],
        _payload: dict[str, Any] | None,
        _timeout: float,
    ) -> tuple[int, str]:
        calls.append(url)
        if url.endswith("/auth/login"):
            return 401, '{"detail":"Invalid credentials"}'
        return 200, json.dumps({"components": {"database": "ok"}})

    checks = smoke.run_local_smoke(
        api_url="http://api.local",
        web_url="http://web.local",
        email="admin@retos.dev",
        password="bad-password",  # noqa: S106 - local fixture password.
        query="Apollo guidance",
        timeout=1,
        requester=requester,
    )

    by_name = {check.name: check for check in checks}
    assert by_name["admin login"].status == "FAIL"
    assert "http://api.local/demo/seed" not in calls


def test_local_smoke_fails_when_demo_search_has_no_hits() -> None:
    smoke = load_local_smoke()

    def requester(
        _method: str,
        url: str,
        _headers: Mapping[str, str],
        _payload: dict[str, Any] | None,
        _timeout: float,
    ) -> tuple[int, str]:
        if url.endswith("/auth/login"):
            return 200, json.dumps({"access_token": "local-token"})
        if url.endswith("/demo/seed"):
            return 200, json.dumps({"domain_id": "domain-demo", "indexed_segments": 4})
        if "/search" in url:
            return 200, json.dumps({"hits": []})
        if "/audit/" in url:
            return 200, json.dumps([{"event_hash": "audit-hash"}])
        if url.endswith("/readyz"):
            return 200, json.dumps({"components": {"database": "ok"}})
        return 200, "{}"

    checks = smoke.run_local_smoke(
        api_url="http://api.local",
        web_url="http://web.local",
        email="admin@retos.dev",
        password="retos-dev-admin-change-me",  # noqa: S106 - local fixture password.
        query="Apollo guidance",
        timeout=1,
        requester=requester,
    )

    failures = {check.name: check.detail for check in checks if check.status == "FAIL"}
    assert failures["demo search"] == "no hits for 'Apollo guidance'"


def test_local_smoke_fails_when_audit_events_are_unhashed() -> None:
    smoke = load_local_smoke()

    def requester(
        _method: str,
        url: str,
        _headers: Mapping[str, str],
        _payload: dict[str, Any] | None,
        _timeout: float,
    ) -> tuple[int, str]:
        if url.endswith("/auth/login"):
            return 200, json.dumps({"access_token": "local-token"})
        if url.endswith("/demo/seed"):
            return 200, json.dumps({"domain_id": "domain-demo", "indexed_segments": 4})
        if "/search" in url:
            return 200, json.dumps({"hits": [{"title": "Apollo Guidance Notes"}]})
        if url.endswith("/readyz"):
            return 200, json.dumps({"components": {"database": "ok"}})
        if "/audit/" in url:
            return 200, json.dumps([{"event_type": "job.created"}])
        return 200, "{}"

    checks = smoke.run_local_smoke(
        api_url="http://api.local",
        web_url="http://web.local",
        email="admin@retos.dev",
        password="retos-dev-admin-change-me",  # noqa: S106 - local fixture password.
        query="Apollo guidance",
        timeout=1,
        requester=requester,
    )

    failures = {check.name: check.detail for check in checks if check.status == "FAIL"}
    assert failures["audit journals"] == "no hash-chain events returned"
    assert failures["audit progress"] == "no hash-chain events returned"
