from dataclasses import dataclass
from datetime import datetime

AdminRole = str
ALLOWED_ADMIN_ROLES = frozenset({"admin", "viewer"})


@dataclass(frozen=True)
class AdminUser:
    id: str
    email: str
    password_hash: str
    roles: tuple[AdminRole, ...]
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AdminUserDomainGrant:
    id: str
    admin_user_id: str
    domain_id: str
    created_at: datetime


def normalize_admin_roles(roles: tuple[str, ...] | list[str]) -> tuple[AdminRole, ...]:
    normalized = tuple(dict.fromkeys(role.strip().lower() for role in roles if role.strip()))
    if not normalized:
        raise ValueError("At least one role is required")
    unsupported = sorted(set(normalized) - ALLOWED_ADMIN_ROLES)
    if unsupported:
        raise ValueError(f"Unsupported admin role(s): {', '.join(unsupported)}")
    return normalized
