import sys
from unittest.mock import MagicMock, patch

# Mock frappe before importing the module
frappe_mock = MagicMock()
sys.modules.setdefault("frappe", frappe_mock)
sys.modules.setdefault("frappe.model", MagicMock())
sys.modules.setdefault("frappe.model.document", MagicMock())

from payroll_indonesia.setup import settings_migration as mig


def test_get_or_create_settings_creates_without_commit():
    frappe_local = MagicMock()
    frappe_local.db.exists.return_value = False
    settings_doc = MagicMock()
    frappe_local.new_doc.return_value = settings_doc

    with patch.object(mig, "frappe", frappe_local):
        assert mig.get_or_create_settings() == settings_doc

    assert settings_doc.insert.called
    assert frappe_local.db.commit.call_count == 0


def test_setup_default_settings_commits_once():
    frappe_local = MagicMock()
    frappe_local.logger.return_value = MagicMock()

    with (
        patch.object(mig, "frappe", frappe_local),
        patch.object(mig, "import_ptkp_table"),
        patch.object(mig, "import_ter_mapping"),
        patch.object(mig, "import_ter_brackets"),
    ):
        mig.setup_default_settings()

    assert frappe_local.db.commit.call_count == 1
