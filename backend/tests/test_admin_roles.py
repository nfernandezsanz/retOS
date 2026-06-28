import pytest

from retos.domain.admin import normalize_admin_roles


def test_normalize_admin_roles_rejects_blank_roles() -> None:
    with pytest.raises(ValueError, match="At least one role is required"):
        normalize_admin_roles([" ", ""])
