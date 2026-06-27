from __future__ import annotations

import os
import sys
import time

import httpx


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    admin_email = os.environ.get("RETOS_BOOTSTRAP_ADMIN_EMAIL", "admin@retos.dev")
    admin_password = os.environ.get("RETOS_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password")
    expect_worker = os.environ.get("RETOS_EXPECT_WORKER", "0") == "1"

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

        ingestion = client.post(
            f"/domains/{domain_id}/ingestions/text",
            headers=auth_headers,
            json={
                "source_id": source_id,
                "title": "Smoke Ingested Text",
                "text": " ".join(f"smoke-token-{index}" for index in range(55)),
                "source_uri": "inline://smoke/ingested.txt",
                "metadata": {"fixture": "api-smoke"},
                "max_segment_tokens": 20,
            },
        )
        require(
            ingestion.status_code == 202,
            f"text ingestion queue failed: {ingestion.status_code} {ingestion.text}",
        )
        ingestion_job = ingestion.json()
        require(ingestion_job["status"] == "queued", "ingestion job should start queued")

        if expect_worker:
            deadline = time.monotonic() + 60
            completed_ingestion = ingestion_job
            while time.monotonic() < deadline:
                fetched = client.get(f"/jobs/{ingestion_job['id']}", headers=auth_headers)
                require(
                    fetched.status_code == 200,
                    f"ingestion job fetch failed: {fetched.status_code} {fetched.text}",
                )
                completed_ingestion = fetched.json()
                if completed_ingestion["status"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(1)
            require(
                completed_ingestion["status"] == "succeeded",
                f"ingestion job did not succeed: {completed_ingestion}",
            )

            ingested_documents = client.get(
                f"/domains/{domain_id}/documents",
                headers=auth_headers,
            )
            require(
                ingested_documents.status_code == 200,
                f"ingested document list failed: {ingested_documents.status_code}",
            )
            ingested_document = next(
                (
                    item
                    for item in ingested_documents.json()
                    if item["title"] == "Smoke Ingested Text"
                ),
                None,
            )
            require(ingested_document is not None, "worker did not persist ingested document")

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
        version_id = listed_versions.json()[0]["id"]

        created_artifact = client.post(
            f"/document-versions/{version_id}/artifacts",
            headers=auth_headers,
            json={
                "kind": "raw_text",
                "uri": "storage://smoke/document/raw.txt",
                "sha256": "sha256:00000002",
                "size_bytes": 42,
            },
        )
        require(
            created_artifact.status_code == 201,
            f"artifact create failed: {created_artifact.status_code} {created_artifact.text}",
        )

        created_segment = client.post(
            f"/document-versions/{version_id}/segments",
            headers=auth_headers,
            json={
                "ordinal": 0,
                "text": "Smoke segment text for search readiness.",
                "anchor": "page=1",
                "token_count": 7,
                "content_hash": "sha256:00000003",
            },
        )
        require(
            created_segment.status_code == 201,
            f"segment create failed: {created_segment.status_code} {created_segment.text}",
        )

        listed_artifacts = client.get(
            f"/document-versions/{version_id}/artifacts",
            headers=auth_headers,
        )
        require(listed_artifacts.status_code == 200, "artifact list failed")
        require(listed_artifacts.json()[0]["kind"] == "raw_text", "missing raw_text artifact")

        listed_segments = client.get(
            f"/document-versions/{version_id}/segments",
            headers=auth_headers,
        )
        require(listed_segments.status_code == 200, "segment list failed")
        require(listed_segments.json()[0]["ordinal"] == 0, "missing first segment")

        search_before_index = client.get(
            f"/domains/{domain_id}/search",
            headers=auth_headers,
            params={"q": "readiness"},
        )
        require(
            search_before_index.status_code == 409,
            f"search should require an index first: {search_before_index.status_code}",
        )

        rebuild_index = client.post(
            f"/domains/{domain_id}/index/rebuild",
            headers=auth_headers,
            json={"run_inline": not expect_worker},
        )
        require(
            rebuild_index.status_code == 202,
            f"index rebuild failed: {rebuild_index.status_code} {rebuild_index.text}",
        )
        index_job = rebuild_index.json()
        require(index_job["kind"] == "index.domain", "invalid index job kind")

        if expect_worker:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                fetched = client.get(f"/jobs/{index_job['id']}", headers=auth_headers)
                require(
                    fetched.status_code == 200,
                    f"index job fetch failed: {fetched.status_code} {fetched.text}",
                )
                index_job = fetched.json()
                if index_job["status"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(1)
        require(index_job["status"] == "succeeded", f"index job did not succeed: {index_job}")

        search_response = client.get(
            f"/domains/{domain_id}/search",
            headers=auth_headers,
            params={"q": "search readiness", "limit": 5},
        )
        require(
            search_response.status_code == 200,
            f"search failed: {search_response.status_code} {search_response.text}",
        )
        search_hits = search_response.json()["hits"]
        require(search_hits, "search returned no hits")
        require(
            search_hits[0]["document_id"] == document["id"],
            "search did not return the expected document",
        )
        require(search_hits[0]["anchor"] == "page=1", "search did not preserve anchors")

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

        started_job = client.post(f"/jobs/{job['id']}/start", headers=auth_headers)
        require(
            started_job.status_code == 200,
            f"job start failed: {started_job.status_code} {started_job.text}",
        )
        require(started_job.json()["status"] == "running", "started job should be running")

        completed_job = client.post(f"/jobs/{job['id']}/complete", headers=auth_headers)
        require(
            completed_job.status_code == 200,
            f"job complete failed: {completed_job.status_code} {completed_job.text}",
        )
        require(completed_job.json()["status"] == "succeeded", "completed job should succeed")

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
                    "system.ready" in line
                    or "document.created" in line
                    or "artifact.created" in line
                    or "segment.created" in line
                    or "ingestion.queued" in line
                    or "ingestion.completed" in line
                    or "index.queued" in line
                    or "index.completed" in line
                    or "job.queued" in line
                    or "job.running" in line
                    or "job.succeeded" in line
                    for line in lines
                ),
                "missing expected progress event",
            )


if __name__ == "__main__":
    main()
