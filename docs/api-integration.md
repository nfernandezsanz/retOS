# API Integration Guide

This guide documents the stable integration surface currently available to the React console, browser smoke tests, and external clients.

## Authentication

All management endpoints require an admin bearer token.

```bash
curl --request POST http://localhost:8000/auth/login \
  --header "Content-Type: application/json" \
  --data '{"email":"admin@retos.dev","password":"retos-dev-admin-change-me"}'
```

Use the returned token as:

```http
Authorization: Bearer <token>
```

## Domains

Create a domain:

```bash
curl --request POST http://localhost:8000/domains \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"slug":"research","name":"Research","description":"Fixture corpus"}'
```

List domains:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/domains
```

Read a domain:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/domains/<domain_id>
```

## Sources

Create a source for a domain:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/sources \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"kind":"mount","name":"Research corpus","uri":"file:///corpus/research"}'
```

Valid `kind` values are `upload`, `mount`, and `url`.

List sources:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/domains/<domain_id>/sources
```

## Progress Events

Long-running workflows expose progress through Server-Sent Events:

```bash
curl --no-buffer \
  --header "Authorization: Bearer <token>" \
  http://localhost:8000/events/progress
```

The browser should reconnect with `Last-Event-ID` when a connection drops.

## Persistence Notes

The API is wired through a SQLAlchemy async Unit of Work. Tests and smoke checks use SQLite with `RETOS_DATABASE_CREATE_ALL=true`. Production-like deployments should use Postgres and managed migrations.
