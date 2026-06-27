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
        auth_headers = {"Authorization": f"Bearer {token}"}

        created_domain = client.post(
            "/domains",
            headers=auth_headers,
            json={
                "slug": "smoke-domain",
                "name": "Smoke Domain",
                "description": "Created by the API smoke test.",
            },
        )
        require(
            created_domain.status_code == 201,
            f"domain create failed: {created_domain.status_code} {created_domain.text}",
        )
        domain = created_domain.json()
        require(domain["slug"] == "smoke-domain", "invalid created domain slug")
        domain_id = domain["id"]

        listed_domains = client.get("/domains", headers=auth_headers)
        require(
            listed_domains.status_code == 200,
            f"domain list failed: {listed_domains.status_code} {listed_domains.text}",
        )
        require(
            any(item["id"] == domain_id for item in listed_domains.json()),
            "created domain missing from list",
        )

        created_source = client.post(
            f"/domains/{domain_id}/sources",
            headers=auth_headers,
            json={
                "kind": "mount",
                "name": "Smoke corpus",
                "uri": "file:///tmp/retos-smoke-corpus",
            },
        )
        require(
            created_source.status_code == 201,
            f"source create failed: {created_source.status_code} {created_source.text}",
        )

        listed_sources = client.get(f"/domains/{domain_id}/sources", headers=auth_headers)
        require(
            listed_sources.status_code == 200,
            f"source list failed: {listed_sources.status_code} {listed_sources.text}",
        )
        require(
            listed_sources.json()[0]["uri"] == "file:///tmp/retos-smoke-corpus",
            "created source missing from list",
        )
        source_id = listed_sources.json()[0]["id"]
        smoke_document_hash = (
            "sha256:0000000000000000000000000000000000000000000000000000000000000001"
        )

        created_document = client.post(
            f"/domains/{domain_id}/documents",
            headers=auth_headers,
            json={
                "source_id": source_id,
                "external_id": "smoke-document-001",
                "title": "Smoke Document",
                "content_hash": smoke_document_hash,
                "source_uri": "file:///tmp/retos-smoke-corpus/document.txt",
                "size_bytes": 42,
                "metadata": {"fixture": True},
            },
        )
        require(
            created_document.status_code == 201,
            f"document create failed: {created_document.status_code} {created_document.text}",
        )
        document = created_document.json()
        require(document["title"] == "Smoke Document", "invalid created document title")

        listed_documents = client.get(f"/domains/{domain_id}/documents", headers=auth_headers)
        require(
            listed_documents.status_code == 200,
            f"document list failed: {listed_documents.status_code} {listed_documents.text}",
        )
        require(
            any(item["id"] == document["id"] for item in listed_documents.json()),
            "created document missing from list",
        )

        listed_versions = client.get(
            f"/documents/{document['id']}/versions",
            headers=auth_headers,
        )
        require(
            listed_versions.status_code == 200,
            f"document versions failed: {listed_versions.status_code} {listed_versions.text}",
        )
        require(listed_versions.json()[0]["version"] == 1, "missing initial document version")

        created_job = client.post(
            "/jobs",
            headers=auth_headers,
            json={
                "kind": "ingest.source",
                "domain_id": domain_id,
                "source_id": source_id,
                "payload": {"source": "api-smoke"},
            },
        )
        require(
            created_job.status_code == 201,
            f"job create failed: {created_job.status_code} {created_job.text}",
        )
        job = created_job.json()
        require(job["status"] == "queued", "created job should be queued")
        require(job["kind"] == "ingest.source", "invalid created job kind")

        listed_jobs = client.get("/jobs", headers=auth_headers)
        require(
            listed_jobs.status_code == 200,
            f"job list failed: {listed_jobs.status_code} {listed_jobs.text}",
        )
        require(any(item["id"] == job["id"] for item in listed_jobs.json()), "job missing")

        stream_timeout = httpx.Timeout(10, read=3)
        with client.stream(
            "GET",
            "/events/progress",
            headers=auth_headers,
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
            require(
                any(
                    "system.ready" in line or "document.created" in line or "job.queued" in line
                    for line in lines
                ),
                "missing expected progress event",
            )


if __name__ == "__main__":
    main()
