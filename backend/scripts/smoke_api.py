from __future__ import annotations

import os
import sys

import httpx


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    admin_email = os.environ.get("RETOS_BOOTSTRAP_ADMIN_EMAIL", "admin@retos.dev")
    admin_password = os.environ.get("RETOS_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password")

    with httpx.Client(base_url=base_url, timeout=10) as client:
        health = client.get("/healthz")
        require(health.status_code == 200, f"healthz failed: {health.status_code}")
        require(health.json() == {"status": "ok", "service": "retos-api"}, "invalid healthz body")

        unauthorized_stream = client.get("/events/progress")
        require(
            unauthorized_stream.status_code == 401,
            f"unauthorized progress stream should fail, got {unauthorized_stream.status_code}",
        )

        login = client.post(
            "/auth/login",
            json={"email": admin_email, "password": admin_password},
        )
        require(login.status_code == 200, f"login failed: {login.status_code} {login.text}")
        token = login.json()["access_token"]
        require(isinstance(token, str) and token, "missing access token")

        stream_timeout = httpx.Timeout(10, read=3)
        with client.stream(
            "GET",
            "/events/progress",
            headers={"Authorization": f"Bearer {token}"},
            timeout=stream_timeout,
        ) as stream:
            require(stream.status_code == 200, f"progress stream failed: {stream.status_code}")
            content_type = stream.headers.get("content-type", "")
            require(
                content_type.startswith("text/event-stream"),
                f"unexpected progress stream content-type: {content_type}",
            )

            lines: list[str] = []
            for line in stream.iter_lines():
                if line:
                    lines.append(line)
                if any(item.startswith("event:") for item in lines) and any(
                    item.startswith("data:") for item in lines
                ):
                    break
            require(lines, "progress stream did not emit any lines")
            require(any("system.ready" in line for line in lines), "missing system.ready event")


if __name__ == "__main__":
    main()
