# Security Policy

## Reporting

Please report security issues privately through GitHub Security Advisories when available.

## Defaults

- Paid LLM calls are disabled by default.
- Production requires a strong JWT secret.
- The development bootstrap admin password is rejected in production.
- Passwords are hashed with Argon2.
- CORS origins must be explicit outside development.

## Sensitive Data

Do not include secrets, raw document contents, or personal data in issue reports unless the maintainer explicitly requests a sanitized sample.
