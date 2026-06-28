from fastapi.testclient import TestClient


def login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_viewer_account(
    client: TestClient,
    admin_headers: dict[str, str],
) -> tuple[str, dict[str, str]]:
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "viewer@retos.dev",
            "password": "viewer-password",
            "roles": ["viewer"],
        },
    )
    assert created.status_code == 201
    return created.json()["id"], login_headers(client, "viewer@retos.dev", "viewer-password")


def grant_domain(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    admin_user_id: str,
    domain_id: str,
) -> None:
    response = client.post(
        f"/admin/users/{admin_user_id}/domain-grants",
        headers=admin_headers,
        json={"domain_id": domain_id},
    )
    assert response.status_code == 201


def seed_operational_records(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    slug: str = "auth-matrix",
) -> tuple[str, str, str]:
    domain = client.post(
        "/domains",
        headers=admin_headers,
        json={"slug": slug, "name": "Authorization Matrix"},
    )
    assert domain.status_code == 201
    domain_id = domain.json()["id"]

    source = client.post(
        f"/domains/{domain_id}/sources",
        headers=admin_headers,
        json={"kind": "mount", "name": "Fixture", "uri": f"file:///{slug}"},
    )
    assert source.status_code == 201
    source_id = source.json()["id"]

    job = client.post(
        "/jobs",
        headers=admin_headers,
        json={
            "kind": "index.domain",
            "domain_id": domain_id,
            "payload": {"reason": "authorization-matrix"},
        },
    )
    assert job.status_code == 201
    return domain_id, source_id, job.json()["id"]


def test_viewer_can_read_granted_operational_state(client: TestClient) -> None:
    admin_headers = login_headers(client, "admin@retos.dev", "test-admin-password")
    domain_id, _, job_id = seed_operational_records(client, admin_headers)
    ungranted_domain_id, _, ungranted_job_id = seed_operational_records(
        client,
        admin_headers,
        slug="ungranted-domain",
    )
    viewer_id, viewer_headers = create_viewer_account(client, admin_headers)
    grant_domain(
        client,
        admin_headers,
        admin_user_id=viewer_id,
        domain_id=domain_id,
    )

    allowed_requests = [
        ("get", "/llm/providers"),
        ("get", "/domains"),
        ("get", f"/domains/{domain_id}"),
        ("get", f"/domains/{domain_id}/sources"),
        ("get", "/jobs"),
        ("get", f"/jobs/{job_id}"),
        ("get", "/audit/journal-events"),
        ("get", "/audit/progress-events"),
        ("get", "/audit/export"),
    ]

    for method, path in allowed_requests:
        response = getattr(client, method)(path, headers=viewer_headers)
        assert response.status_code == 200, path

    listed_domains = client.get("/domains", headers=viewer_headers)
    assert [domain["id"] for domain in listed_domains.json()] == [domain_id]

    forbidden_requests = [
        f"/domains/{ungranted_domain_id}",
        f"/domains/{ungranted_domain_id}/sources",
        f"/jobs/{ungranted_job_id}",
        "/evals/runs",
        "/evals/runs/compare?baseline_job_id=job-a&candidate_job_id=job-b",
    ]
    for path in forbidden_requests:
        response = client.get(path, headers=viewer_headers)
        assert response.status_code == 403, path


def test_viewer_cannot_mutate_operational_state(client: TestClient) -> None:
    admin_headers = login_headers(client, "admin@retos.dev", "test-admin-password")
    domain_id, source_id, job_id = seed_operational_records(client, admin_headers)
    viewer_id, viewer_headers = create_viewer_account(client, admin_headers)
    grant_domain(
        client,
        admin_headers,
        admin_user_id=viewer_id,
        domain_id=domain_id,
    )

    forbidden_requests = [
        (
            "post",
            "/domains",
            {"json": {"slug": "viewer-write", "name": "Viewer Write"}},
        ),
        (
            "post",
            f"/domains/{domain_id}/sources",
            {"json": {"kind": "upload", "name": "Upload", "uri": "upload://viewer"}},
        ),
        (
            "post",
            "/jobs",
            {"json": {"kind": "index.domain", "domain_id": domain_id, "payload": {}}},
        ),
        ("post", f"/jobs/{job_id}/start", {}),
        ("post", f"/jobs/{job_id}/retry", {}),
        (
            "post",
            f"/domains/{domain_id}/ingestions/text",
            {
                "json": {
                    "source_id": source_id,
                    "title": "Viewer text",
                    "text": "Viewer cannot ingest text.",
                }
            },
        ),
        ("post", f"/domains/{domain_id}/index/rebuild", {"json": {"run_inline": False}}),
        (
            "post",
            f"/domains/{domain_id}/queries",
            {"json": {"question": "What is in the corpus?", "run_inline": False}},
        ),
        ("post", "/evals/smoke", {}),
        ("get", "/admin/users", {}),
    ]

    for method, path, kwargs in forbidden_requests:
        response = getattr(client, method)(path, headers=viewer_headers, **kwargs)
        assert response.status_code == 403, path


def test_revoked_domain_grant_removes_viewer_visibility(client: TestClient) -> None:
    admin_headers = login_headers(client, "admin@retos.dev", "test-admin-password")
    domain_id, _, _ = seed_operational_records(client, admin_headers)
    viewer_id, viewer_headers = create_viewer_account(client, admin_headers)
    grant_domain(
        client,
        admin_headers,
        admin_user_id=viewer_id,
        domain_id=domain_id,
    )

    before_revoke = client.get("/domains", headers=viewer_headers)
    revoked = client.delete(
        f"/admin/users/{viewer_id}/domain-grants/{domain_id}",
        headers=admin_headers,
    )
    after_revoke = client.get("/domains", headers=viewer_headers)

    assert before_revoke.status_code == 200
    assert [domain["id"] for domain in before_revoke.json()] == [domain_id]
    assert revoked.status_code == 204
    assert after_revoke.status_code == 200
    assert after_revoke.json() == []
