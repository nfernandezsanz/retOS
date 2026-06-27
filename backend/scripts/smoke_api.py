from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pymupdf


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def wait_for_job(
    client: httpx.Client,
    *,
    job_id: str,
    headers: dict[str, str],
    timeout_seconds: int = 60,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    job: dict[str, object] = {}
    while time.monotonic() < deadline:
        fetched = client.get(f"/jobs/{job_id}", headers=headers)
        require(fetched.status_code == 200, f"job fetch failed: {fetched.status_code}")
        job = fetched.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(1)
    return job


def prepare_scan_source() -> tuple[str, Path | None]:
    configured = os.environ.get("RETOS_SMOKE_SCAN_SOURCE_URI")
    if configured is not None:
        return configured, None

    root = Path(tempfile.mkdtemp(prefix="retos-smoke-corpus-"))
    (root / "apollo-notes.txt").write_text(
        "Apollo guidance computers used deterministic checklists.",
        encoding="utf-8",
    )
    (root / "biology.md").write_text(
        "# Biology\n\nOcean biology notes mention plankton and salinity.",
        encoding="utf-8",
    )
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Mars rover sample caching mission brief.")
    document.save(root / "mission-brief.pdf")
    document.close()
    return root.as_uri(), root


def prepare_squad_dataset() -> Path:
    dataset_root = Path(os.environ["RETOS_EVAL_DATASET_ROOT"])
    dataset_root.mkdir(parents=True, exist_ok=True)
    dataset_path = dataset_root / "smoke-squad.json"
    dataset_path.write_text(
        json.dumps(
            {
                "version": "v2.0",
                "data": [
                    {
                        "title": "Solar System",
                        "paragraphs": [
                            {
                                "context": (
                                    "Mars is called the Red Planet because iron oxide dust "
                                    "covers much of its surface."
                                ),
                                "qas": [
                                    {
                                        "id": "mars-red-planet",
                                        "question": "Why is Mars called the Red Planet?",
                                        "answers": [
                                            {"text": "iron oxide dust", "answer_start": 39}
                                        ],
                                        "is_impossible": False,
                                    },
                                    {
                                        "id": "mars-ocean-depth",
                                        "question": "How deep are the oceans on Mars today?",
                                        "answers": [],
                                        "is_impossible": True,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return dataset_path


def main() -> None:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    admin_email = os.environ.get("RETOS_BOOTSTRAP_ADMIN_EMAIL", "admin@retos.dev")
    admin_password = os.environ.get("RETOS_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password")
    expect_worker = os.environ.get("RETOS_EXPECT_WORKER", "0") == "1"
    prepare_squad = os.environ.get("RETOS_SMOKE_PREPARE_SQUAD_DATASET", "1") == "1"
    check_report_files = os.environ.get("RETOS_SMOKE_CHECK_REPORT_FILES", "1") == "1"
    scan_source_uri, temp_scan_root = prepare_scan_source()
    if prepare_squad:
        prepare_squad_dataset()

    try:
        with httpx.Client(base_url=base_url, timeout=10) as client:
            health = client.get("/healthz")
            require(health.status_code == 200, f"healthz failed: {health.status_code}")
            require(
                health.json() == {"status": "ok", "service": "retos-api"},
                "invalid healthz body",
            )

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

            provider_catalog = client.get("/llm/providers", headers=auth_headers)
            require(
                provider_catalog.status_code == 200,
                f"provider catalog failed: {provider_catalog.status_code} {provider_catalog.text}",
            )
            providers = provider_catalog.json()
            require(providers["active"]["provider"] == "local", "invalid active provider")
            require(providers["active"]["paid"] is False, "local provider should not be paid")
            require(
                any(item["name"] == "local" and item["enabled"] for item in providers["providers"]),
                "local provider missing from catalog",
            )

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
                json={"kind": "mount", "name": "Smoke corpus", "uri": scan_source_uri},
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
            require(listed_sources.json()[0]["uri"] == scan_source_uri, "source missing")
            source_id = listed_sources.json()[0]["id"]

            scan_source = client.post(
                f"/sources/{source_id}/scan",
                headers=auth_headers,
                json={"max_segment_tokens": 20},
            )
            require(
                scan_source.status_code == 202,
                f"source scan failed: {scan_source.status_code} {scan_source.text}",
            )
            scan_job = scan_source.json()
            require(scan_job["kind"] == "ingest.source", "invalid scan job kind")
            if expect_worker:
                scan_job = wait_for_job(client, job_id=scan_job["id"], headers=auth_headers)
            require(scan_job["status"] == "succeeded", f"scan job did not succeed: {scan_job}")

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
                completed_ingestion = wait_for_job(
                    client,
                    job_id=ingestion_job["id"],
                    headers=auth_headers,
                )
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
                require(
                    any(
                        item["title"] == "Smoke Ingested Text" for item in ingested_documents.json()
                    ),
                    "worker did not persist ingested document",
                )

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
            require(listed_versions.json()[0]["version"] == 1, "missing initial version")
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
            require(listed_artifacts.json()[0]["kind"] == "raw_text", "missing artifact")

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
                index_job = wait_for_job(client, job_id=index_job["id"], headers=auth_headers)
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
            require(search_hits[0]["document_id"] == document["id"], "unexpected search document")
            require(search_hits[0]["anchor"] == "page=1", "search did not preserve anchors")

            agent_query = client.post(
                f"/domains/{domain_id}/queries",
                headers=auth_headers,
                json={
                    "question": "What evidence mentions search readiness?",
                    "limit": 5,
                    "run_inline": not expect_worker,
                },
            )
            require(
                agent_query.status_code == 202,
                f"agent query failed: {agent_query.status_code} {agent_query.text}",
            )
            agent_job = agent_query.json()["job"]
            require(agent_job["kind"] == "agent.query", "invalid agent job kind")
            if expect_worker:
                agent_job = wait_for_job(client, job_id=agent_job["id"], headers=auth_headers)
                require(
                    agent_job["status"] == "succeeded",
                    f"agent job did not succeed: {agent_job}",
                )
                agent_result = agent_job["payload"]["result"]
            else:
                require(
                    agent_query.json()["result"] is not None,
                    "inline agent query did not return a result",
                )
                agent_result = agent_query.json()["result"]
            require(
                agent_result["citations"],
                "agent query returned no citations",
            )
            require(
                "search readiness" in agent_result["answer"],
                "agent answer did not include grounded evidence",
            )

            eval_smoke = client.post("/evals/smoke", headers=auth_headers)
            require(
                eval_smoke.status_code == 202,
                f"eval smoke failed: {eval_smoke.status_code} {eval_smoke.text}",
            )
            eval_body = eval_smoke.json()
            require(eval_body["job"]["kind"] == "eval.run", "invalid eval job kind")
            require(eval_body["job"]["status"] == "succeeded", "eval job did not succeed")
            require(eval_body["report"]["passed"] is True, "eval report did not pass")
            require(eval_body["report"]["case_count"] == 3, "unexpected eval case count")

            squad_eval = client.post(
                "/evals/squad",
                headers=auth_headers,
                json={
                    "dataset_path": "smoke-squad.json",
                    "max_cases": 2,
                    "write_report": True,
                    "report_stem": "api-smoke-squad",
                },
            )
            require(
                squad_eval.status_code == 202,
                f"SQuAD eval failed: {squad_eval.status_code} {squad_eval.text}",
            )
            squad_body = squad_eval.json()
            require(squad_body["job"]["kind"] == "eval.run", "invalid SQuAD eval job kind")
            require(squad_body["job"]["status"] == "succeeded", "SQuAD eval did not succeed")
            require(squad_body["report"]["suite_name"] == "squad-v2", "invalid SQuAD suite")
            require(squad_body["report"]["case_count"] == 2, "unexpected SQuAD case count")
            require(squad_body["report_paths"], "SQuAD eval did not return report paths")
            if check_report_files:
                require(
                    Path(squad_body["report_paths"]["json"]).exists(),
                    "SQuAD JSON report was not written",
                )
                require(
                    Path(squad_body["report_paths"]["markdown"]).exists(),
                    "SQuAD Markdown report was not written",
                )

            eval_runs = client.get("/evals/runs", headers=auth_headers)
            require(
                eval_runs.status_code == 200,
                f"eval runs failed: {eval_runs.status_code} {eval_runs.text}",
            )
            latest_eval_run = eval_runs.json()[0]
            require(
                latest_eval_run["job"]["id"] == squad_body["job"]["id"],
                "latest eval run did not match SQuAD eval",
            )
            require(
                latest_eval_run["report"]["passed"] is True,
                "latest eval run report did not pass",
            )

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
            require(
                completed_job.json()["status"] == "succeeded",
                "completed job should succeed",
            )

            listed_jobs = client.get("/jobs", headers=auth_headers)
            require(
                listed_jobs.status_code == 200,
                f"job list failed: {listed_jobs.status_code} {listed_jobs.text}",
            )
            require(any(item["id"] == job["id"] for item in listed_jobs.json()), "job missing")

            journal_events = client.get(
                "/audit/journal-events",
                headers=auth_headers,
                params={"limit": 20},
            )
            require(
                journal_events.status_code == 200,
                f"journal events failed: {journal_events.status_code} {journal_events.text}",
            )
            journal_body = journal_events.json()
            require(
                any(
                    item["event_type"] == "job.created" and item["entity_id"] == job["id"]
                    for item in journal_body
                ),
                "created job missing from journal events",
            )

            persisted_progress_events = client.get(
                "/audit/progress-events",
                headers=auth_headers,
                params={"limit": 20},
            )
            require(
                persisted_progress_events.status_code == 200,
                "persisted progress events failed: "
                f"{persisted_progress_events.status_code} {persisted_progress_events.text}",
            )
            progress_body = persisted_progress_events.json()
            require(
                any(
                    item["event_type"] == "job.queued" and item["job_id"] == job["id"]
                    for item in progress_body
                ),
                "created job missing from persisted progress events",
            )

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
                    any(item.startswith("event:") for item in lines)
                    and any(item.startswith("data:") for item in lines),
                    f"progress stream did not emit an SSE event/data pair: {lines}",
                )
    finally:
        if temp_scan_root is not None:
            shutil.rmtree(temp_scan_root, ignore_errors=True)


if __name__ == "__main__":
    main()
