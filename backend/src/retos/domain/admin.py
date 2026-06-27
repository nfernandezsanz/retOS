from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdminUser:
    id: str
    email: str
    password_hash: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
