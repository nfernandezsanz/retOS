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


def prepare_hotpotqa_dataset() -> Path:
    dataset_root = Path(os.environ["RETOS_EVAL_DATASET_ROOT"])
    dataset_root.mkdir(parents=True, exist_ok=True)
    dataset_path = dataset_root / "smoke-hotpotqa.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "_id": "vela-air-force",
                    "question": (
                        "Which agency operated Vela spacecraft in the United States "
                        "Air Force history?"
                    ),
                    "answer": "United States Air Force",
                    "supporting_facts": [["Vela", 0], ["United States Air Force", 0]],
                    "context": [
                        [
                            "Vela",
                            [
                                "Vela spacecraft were satellites operated by "
                                "the United States Air Force."
                            ],
                        ],
                        [
                            "United States Air Force",
                            ["The United States Air Force operated satellite programs."],
                        ],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return dataset_path


def prepare_natural_questions_dataset() -> Path:
    dataset_root = Path(os.environ["RETOS_EVAL_DATASET_ROOT"])
    dataset_root.mkdir(parents=True, exist_ok=True)
    dataset_path = dataset_root / "smoke-nq.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": 123,
                "question_text": "Which star is Mercury closest to?",
                "document_title": "Mercury (planet)",
                "document_text": (
                    "Mercury is the closest planet to the Sun and has a short orbital year."
                ),
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 14},
                        "short_answers": [{"start_token": 7, "end_token": 8}],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return dataset_path


def prepare_ocr_benchmark_dataset() -> Path:
    dataset_root = Path(os.environ["RETOS_EVAL_DATASET_ROOT"]) / "ocr-benchmark"
    dataset_root.mkdir(parents=True, exist_ok=True)
    pdf_path = dataset_root / "receipt-001.pdf"
    document = pymupdf.open()
    page = document.new_page(width=1200, height=800)
    page.insert_text(
        (72, 160),
        "Receipt total forty two dollars.",
        fontsize=36,
    )
    document.save(pdf_path)
    document.close()
    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "receipt-001",
                        "input_path": pdf_path.name,
                        "expected_text": "Receipt total forty two dollars.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def main() -> None:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    admin_email = os.environ.get("RETOS_BOOTSTRAP_ADMIN_EMAIL", "admin@retos.dev")
    admin_password = os.environ.get("RETOS_BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password")
    expect_worker = os.environ.get("RETOS_EXPECT_WORKER", "0") == "1"
    prepare_datasets = os.environ.get("RETOS_SMOKE_PREPARE_DATASETS", "1") == "1"
    check_report_files = os.environ.get("RETOS_SMOKE_CHECK_REPORT_FILES", "1") == "1"
    run_ocr_benchmark = os.environ.get("RETOS_SMOKE_RUN_OCR_BENCHMARK", "0") == "1"
    scan_source_uri, temp_scan_root = prepare_scan_source()
    if prepare_datasets:
        prepare_squad_dataset()
        prepare_hotpotqa_dataset()
        prepare_natural_questions_dataset()
        if run_ocr_benchmark:
            prepare_ocr_benchmark_dataset()

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

            admin_users = client.get("/admin/users", headers=auth_headers)
            require(
                admin_users.status_code == 200,
                f"admin user list failed: {admin_users.status_code} {admin_users.text}",
            )
            require(
                any(user["email"] == admin_email.lower() for user in admin_users.json()),
                "bootstrap admin missing from admin user list",
            )
            smoke_admin = client.post(
                "/admin/users",
                headers=auth_headers,
                json={
                    "email": "smoke-admin@retos.dev",
                    "password": "smoke-admin-password",
                },
            )
            require(
                smoke_admin.status_code == 201,
                f"admin user create failed: {smoke_admin.status_code} {smoke_admin.text}",
            )
            smoke_admin_body = smoke_admin.json()
            smoke_admin_login = client.post(
                "/auth/login",
                json={
                    "email": "smoke-admin@retos.dev",
                    "password": "smoke-admin-password",
                },
            )
            require(
                smoke_admin_login.status_code == 200,
                "created admin login failed: "
                f"{smoke_admin_login.status_code} {smoke_admin_login.text}",
            )
            disabled_smoke_admin = client.patch(
                f"/admin/users/{smoke_admin_body['id']}/status",
                headers=auth_headers,
                json={"is_active": False},
            )
            require(
                disabled_smoke_admin.status_code == 200,
                "admin user disable failed: "
                f"{disabled_smoke_admin.status_code} {disabled_smoke_admin.text}",
            )
            disabled_login = client.post(
                "/auth/login",
                json={
                    "email": "smoke-admin@retos.dev",
                    "password": "smoke-admin-password",
                },
            )
            require(disabled_login.status_code == 401, "disabled admin login should fail")

            smoke_viewer = client.post(
                "/admin/users",
                headers=auth_headers,
                json={
                    "email": "smoke-viewer@retos.dev",
                    "password": "smoke-viewer-password",
                    "roles": ["viewer"],
                },
            )
            require(
                smoke_viewer.status_code == 201,
                f"viewer user create failed: {smoke_viewer.status_code} {smoke_viewer.text}",
            )
            smoke_viewer_body = smoke_viewer.json()
            smoke_viewer_login = client.post(
                "/auth/login",
                json={
                    "email": "smoke-viewer@retos.dev",
                    "password": "smoke-viewer-password",
                },
            )
            require(
                smoke_viewer_login.status_code == 200,
                "created viewer login failed: "
                f"{smoke_viewer_login.status_code} {smoke_viewer_login.text}",
            )
            viewer_headers = {
                "Authorization": f"Bearer {smoke_viewer_login.json()['access_token']}"
            }

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

            viewer_domain_grant = client.post(
                f"/admin/users/{smoke_viewer_body['id']}/domain-grants",
                headers=auth_headers,
                json={"domain_id": domain_id},
            )
            require(
                viewer_domain_grant.status_code == 201,
                "viewer domain grant failed: "
                f"{viewer_domain_grant.status_code} {viewer_domain_grant.text}",
            )

            viewer_provider_catalog = client.get("/llm/providers", headers=viewer_headers)
            require(
                viewer_provider_catalog.status_code == 200,
                "viewer provider catalog failed: "
                f"{viewer_provider_catalog.status_code} {viewer_provider_catalog.text}",
            )
            viewer_domains = client.get("/domains", headers=viewer_headers)
            require(
                viewer_domains.status_code == 200,
                f"viewer domain list failed: {viewer_domains.status_code} {viewer_domains.text}",
            )
            viewer_sources = client.get(
                f"/domains/{domain_id}/sources",
                headers=viewer_headers,
            )
            require(
                viewer_sources.status_code == 200,
                f"viewer source list failed: {viewer_sources.status_code} {viewer_sources.text}",
            )
            viewer_admin_list = client.get("/admin/users", headers=viewer_headers)
            require(
                viewer_admin_list.status_code == 403,
                f"viewer admin list should fail: {viewer_admin_list.status_code}",
            )
            viewer_domain_create = client.post(
                "/domains",
                headers=viewer_headers,
                json={"slug": "viewer-write", "name": "Viewer Write"},
            )
            require(
                viewer_domain_create.status_code == 403,
                f"viewer domain create should fail: {viewer_domain_create.status_code}",
            )

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

            uploaded = client.post(
                f"/domains/{domain_id}/ingestions/upload",
                headers=auth_headers,
                data={"title": "Smoke Uploaded File", "max_segment_tokens": "20"},
                files={
                    "file": (
                        "smoke-upload.txt",
                        b"Uploaded smoke fixture mentions citations and audit trails.",
                        "text/plain",
                    )
                },
            )
            require(
                uploaded.status_code == 202,
                f"file upload queue failed: {uploaded.status_code} {uploaded.text}",
            )
            upload_job = uploaded.json()
            require(upload_job["kind"] == "ingest.source", "invalid upload job kind")
            if expect_worker:
                upload_job = wait_for_job(client, job_id=upload_job["id"], headers=auth_headers)
            require(
                upload_job["status"] == "succeeded", f"upload job did not succeed: {upload_job}"
            )

            uploaded_documents = client.get(
                f"/domains/{domain_id}/documents",
                headers=auth_headers,
            )
            require(
                uploaded_documents.status_code == 200,
                f"uploaded document list failed: {uploaded_documents.status_code}",
            )
            require(
                any(item["title"] == "Smoke Uploaded File" for item in uploaded_documents.json()),
                "uploaded document missing from list",
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
            require(
                "neighbor_context" in agent_result,
                "agent result did not include neighbor context",
            )

            updated_document = client.patch(
                f"/documents/{document['id']}",
                headers=auth_headers,
                json={
                    "title": "Smoke Document Reviewed",
                    "metadata": {"fixture": True, "reviewed": True},
                },
            )
            require(
                updated_document.status_code == 200,
                f"document update failed: {updated_document.status_code} {updated_document.text}",
            )
            require(
                updated_document.json()["title"] == "Smoke Document Reviewed",
                "document update did not persist title",
            )

            archived_document = client.delete(
                f"/documents/{document['id']}",
                headers=auth_headers,
            )
            require(
                archived_document.status_code == 200,
                "document archive failed: "
                f"{archived_document.status_code} {archived_document.text}",
            )
            require(
                archived_document.json()["archived_at"] is not None,
                "document archive did not set archived_at",
            )
            active_documents = client.get(f"/domains/{domain_id}/documents", headers=auth_headers)
            require(active_documents.status_code == 200, "active document list failed")
            require(
                all(item["id"] != document["id"] for item in active_documents.json()),
                "archived document remained in active list",
            )
            archived_documents = client.get(
                f"/domains/{domain_id}/documents",
                headers=auth_headers,
                params={"include_archived": "true"},
            )
            require(archived_documents.status_code == 200, "archived document list failed")
            require(
                any(item["id"] == document["id"] for item in archived_documents.json()),
                "archived document missing from include_archived list",
            )
            restored_document = client.post(
                f"/documents/{document['id']}/restore",
                headers=auth_headers,
            )
            require(
                restored_document.status_code == 200,
                "document restore failed: "
                f"{restored_document.status_code} {restored_document.text}",
            )
            require(
                restored_document.json()["archived_at"] is None,
                "document restore did not clear archived_at",
            )
            restored_documents = client.get(
                f"/domains/{domain_id}/documents",
                headers=auth_headers,
            )
            require(restored_documents.status_code == 200, "restored document list failed")
            require(
                any(item["id"] == document["id"] for item in restored_documents.json()),
                "restored document missing from active list",
            )
            document_history = client.get(
                f"/documents/{document['id']}/history",
                headers=auth_headers,
            )
            require(
                document_history.status_code == 200,
                f"document history failed: {document_history.status_code} {document_history.text}",
            )
            history_events = document_history.json()["events"]
            require(
                [event["event_type"] for event in history_events][-3:]
                == ["document.updated", "document.archived", "document.restored"],
                "document history did not include update/archive/restore events",
            )
            require(
                any(
                    change["field"] == "title" and change["after"] == "Smoke Document Reviewed"
                    for change in history_events[-3]["changes"]
                ),
                "document history did not include title diff",
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

            hotpotqa_eval = client.post(
                "/evals/hotpotqa",
                headers=auth_headers,
                json={
                    "dataset_path": "smoke-hotpotqa.json",
                    "max_cases": 1,
                    "write_report": True,
                    "report_stem": "api-smoke-hotpotqa",
                },
            )
            require(
                hotpotqa_eval.status_code == 202,
                f"HotpotQA eval failed: {hotpotqa_eval.status_code} {hotpotqa_eval.text}",
            )
            hotpotqa_body = hotpotqa_eval.json()
            require(
                hotpotqa_body["job"]["kind"] == "eval.run",
                "invalid HotpotQA eval job kind",
            )
            require(
                hotpotqa_body["job"]["status"] == "succeeded",
                "HotpotQA eval did not succeed",
            )
            require(
                hotpotqa_body["report"]["suite_name"] == "hotpotqa",
                "invalid HotpotQA suite",
            )
            require(
                hotpotqa_body["report"]["case_count"] == 1,
                "unexpected HotpotQA case count",
            )
            require(hotpotqa_body["report_paths"], "HotpotQA eval did not return report paths")
            if check_report_files:
                require(
                    Path(hotpotqa_body["report_paths"]["json"]).exists(),
                    "HotpotQA JSON report was not written",
                )
                require(
                    Path(hotpotqa_body["report_paths"]["markdown"]).exists(),
                    "HotpotQA Markdown report was not written",
                )

            nq_eval = client.post(
                "/evals/natural-questions",
                headers=auth_headers,
                json={
                    "dataset_path": "smoke-nq.jsonl",
                    "max_cases": 1,
                    "write_report": True,
                    "report_stem": "api-smoke-natural-questions",
                },
            )
            require(
                nq_eval.status_code == 202,
                f"Natural Questions eval failed: {nq_eval.status_code} {nq_eval.text}",
            )
            nq_body = nq_eval.json()
            require(
                nq_body["job"]["kind"] == "eval.run",
                "invalid Natural Questions eval job kind",
            )
            require(
                nq_body["job"]["status"] == "succeeded",
                "Natural Questions eval did not succeed",
            )
            require(
                nq_body["report"]["suite_name"] == "natural-questions",
                "invalid Natural Questions suite",
            )
            require(
                nq_body["report"]["case_count"] == 1,
                "unexpected Natural Questions case count",
            )
            require(
                nq_body["report_paths"],
                "Natural Questions eval did not return report paths",
            )
            if check_report_files:
                require(
                    Path(nq_body["report_paths"]["json"]).exists(),
                    "Natural Questions JSON report was not written",
                )
                require(
                    Path(nq_body["report_paths"]["markdown"]).exists(),
                    "Natural Questions Markdown report was not written",
                )

            latest_eval_body = nq_body
            if run_ocr_benchmark:
                ocr_benchmark_eval = client.post(
                    "/evals/ocr-benchmark",
                    headers=auth_headers,
                    json={
                        "dataset_path": "ocr-benchmark/manifest.json",
                        "dataset_format": "manifest",
                        "max_cases": 1,
                        "write_report": True,
                        "report_stem": "api-smoke-ocr-benchmark",
                        "max_character_error_rate": 0.20,
                        "max_word_error_rate": 0.35,
                        "max_pages": 1,
                    },
                )
                require(
                    ocr_benchmark_eval.status_code == 202,
                    "OCR benchmark eval failed: "
                    f"{ocr_benchmark_eval.status_code} {ocr_benchmark_eval.text}",
                )
                ocr_benchmark_body = ocr_benchmark_eval.json()
                require(
                    ocr_benchmark_body["job"]["kind"] == "eval.run",
                    "invalid OCR benchmark eval job kind",
                )
                require(
                    ocr_benchmark_body["job"]["status"] == "succeeded",
                    "OCR benchmark eval did not succeed",
                )
                require(
                    ocr_benchmark_body["report"]["suite_name"] == "ocr-manifest",
                    "invalid OCR benchmark suite",
                )
                require(
                    ocr_benchmark_body["report"]["case_count"] == 1,
                    "unexpected OCR benchmark case count",
                )
                require(
                    ocr_benchmark_body["report_paths"],
                    "OCR benchmark eval did not return report paths",
                )
                if check_report_files:
                    require(
                        Path(ocr_benchmark_body["report_paths"]["json"]).exists(),
                        "OCR benchmark JSON report was not written",
                    )
                    require(
                        Path(ocr_benchmark_body["report_paths"]["markdown"]).exists(),
                        "OCR benchmark Markdown report was not written",
                    )
                latest_eval_body = ocr_benchmark_body

            eval_runs = client.get("/evals/runs", headers=auth_headers)
            require(
                eval_runs.status_code == 200,
                f"eval runs failed: {eval_runs.status_code} {eval_runs.text}",
            )
            latest_eval_run = eval_runs.json()[0]
            require(
                latest_eval_run["job"]["id"] == latest_eval_body["job"]["id"],
                "latest eval run did not match the most recent eval",
            )
            require(
                latest_eval_run["report"]["passed"] is True,
                "latest eval run report did not pass",
            )
            eval_rerun = client.post(
                f"/evals/runs/{latest_eval_body['job']['id']}/rerun",
                headers=auth_headers,
            )
            require(
                eval_rerun.status_code == 202,
                f"eval rerun failed: {eval_rerun.status_code} {eval_rerun.text}",
            )
            eval_rerun_body = eval_rerun.json()
            require(
                eval_rerun_body["job"]["id"] != latest_eval_body["job"]["id"],
                "eval rerun reused the original job id",
            )
            require(
                eval_rerun_body["job"]["payload"]["rerun_from_job_id"]
                == latest_eval_body["job"]["id"],
                "eval rerun did not persist origin job id",
            )
            eval_runs_after_rerun = client.get("/evals/runs", headers=auth_headers)
            require(
                eval_runs_after_rerun.status_code == 200,
                "eval runs after rerun failed: "
                f"{eval_runs_after_rerun.status_code} {eval_runs_after_rerun.text}",
            )
            require(
                eval_runs_after_rerun.json()[0]["job"]["id"] == eval_rerun_body["job"]["id"],
                "latest eval run did not match rerun job",
            )
            eval_comparison = client.get(
                "/evals/runs/compare",
                headers=auth_headers,
                params={
                    "baseline_job_id": eval_body["job"]["id"],
                    "candidate_job_id": nq_body["job"]["id"],
                },
            )
            require(
                eval_comparison.status_code == 200,
                f"eval comparison failed: {eval_comparison.status_code} {eval_comparison.text}",
            )
            comparison_body = eval_comparison.json()
            require(
                comparison_body["baseline"]["job_id"] == eval_body["job"]["id"],
                "eval comparison baseline did not match smoke eval",
            )
            require(
                comparison_body["candidate"]["job_id"] == nq_body["job"]["id"],
                "eval comparison candidate did not match Natural Questions eval",
            )
            require(
                any(metric["name"] == "retrieval_recall" for metric in comparison_body["metrics"]),
                "eval comparison did not include retrieval recall",
            )
            eval_trends = client.get("/evals/runs/trends", headers=auth_headers)
            require(
                eval_trends.status_code == 200,
                f"eval trends failed: {eval_trends.status_code} {eval_trends.text}",
            )
            trend_body = eval_trends.json()
            require(
                any(item["suite_name"] == "retos-smoke" for item in trend_body),
                "eval trends did not include smoke suite",
            )
            require(
                any(
                    metric["name"] == "retrieval_recall"
                    for item in trend_body
                    for metric in item["metrics"]
                ),
                "eval trends did not include retrieval recall",
            )
            require(
                any(item["run_count"] >= 2 for item in trend_body),
                "eval trends did not include rerun history",
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

            retry_seed = client.post(
                "/jobs",
                headers=auth_headers,
                json={
                    "kind": "index.domain",
                    "domain_id": domain_id,
                    "payload": {"requested_at": "api-smoke-retry"},
                },
            )
            require(
                retry_seed.status_code == 201,
                f"retry seed create failed: {retry_seed.status_code} {retry_seed.text}",
            )
            retry_seed_body = retry_seed.json()
            started_retry_seed = client.post(
                f"/jobs/{retry_seed_body['id']}/start",
                headers=auth_headers,
            )
            require(
                started_retry_seed.status_code == 200,
                "retry seed start failed: "
                f"{started_retry_seed.status_code} {started_retry_seed.text}",
            )
            failed_retry_seed = client.post(
                f"/jobs/{retry_seed_body['id']}/fail",
                headers=auth_headers,
                json={"error": "api smoke retry seed"},
            )
            require(
                failed_retry_seed.status_code == 200,
                "retry seed fail failed: "
                f"{failed_retry_seed.status_code} {failed_retry_seed.text}",
            )
            retried_job = client.post(
                f"/jobs/{retry_seed_body['id']}/retry",
                headers=auth_headers,
            )
            require(
                retried_job.status_code == 202,
                f"job retry failed: {retried_job.status_code} {retried_job.text}",
            )
            retried_body = retried_job.json()
            require(retried_body["status"] == "queued", "retried job should be queued")
            require(
                retried_body["payload"]["retried_from_job_id"] == retry_seed_body["id"],
                "retried job did not link original job",
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

            audit_export = client.get(
                "/audit/export",
                headers=auth_headers,
                params={"limit": 20},
            )
            require(
                audit_export.status_code == 200,
                f"audit export failed: {audit_export.status_code} {audit_export.text}",
            )
            require(
                audit_export.headers.get("cache-control") == "no-store",
                "audit export should disable caching",
            )
            audit_export_body = audit_export.json()
            require(
                audit_export_body["schema_version"] == "retos.audit-export.v1",
                "unexpected audit export schema version",
            )
            require(
                any(
                    item["event_type"] == "job.created" and item["entity_id"] == job["id"]
                    for item in audit_export_body["journal_events"]
                ),
                "created job missing from audit export journal events",
            )
            require(
                any(
                    item["event_type"] == "job.queued" and item["job_id"] == job["id"]
                    for item in audit_export_body["progress_events"]
                ),
                "created job missing from audit export progress events",
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
                replay_id = next(
                    (item.removeprefix("id:").strip() for item in lines if item.startswith("id:")),
                    "",
                )
                require(
                    replay_id.startswith(("progress:", "live:")),
                    f"progress stream emitted unexpected id: {replay_id}",
                )

            with client.stream(
                "GET",
                "/events/progress",
                headers={**auth_headers, "Last-Event-ID": replay_id},
                timeout=stream_timeout,
            ) as resumed_stream:
                require(
                    resumed_stream.status_code == 200,
                    f"resumed progress stream failed: {resumed_stream.status_code}",
                )
                resumed_lines: list[str] = []
                for line in resumed_stream.iter_lines():
                    if line:
                        resumed_lines.append(line)
                    if any(item.startswith("event:") for item in resumed_lines) and any(
                        item.startswith("data:") for item in resumed_lines
                    ):
                        break
                require(
                    resumed_lines,
                    "resumed progress stream did not emit any lines",
                )
    finally:
        if temp_scan_root is not None:
            shutil.rmtree(temp_scan_root, ignore_errors=True)


if __name__ == "__main__":
    main()
