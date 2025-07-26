import sys
from unittest.mock import MagicMock, patch

import pytest

frappe_import_mock = MagicMock()
sys.modules["frappe"] = frappe_import_mock
sys.modules["frappe.model"] = MagicMock()
sys.modules["frappe.model.document"] = MagicMock()

from payroll_indonesia.payroll_indonesia.setup import setup_module as setup_mod


def test_ensure_parent_idempotent():
    frappe_mock = MagicMock()

    # First call should create the parent, second should detect existing
    frappe_mock.db.exists.side_effect = [False, True]

    doc_mock = MagicMock()
    doc_mock.root_type = "Expense"
    doc_mock.report_type = "Profit and Loss"
    frappe_mock.get_doc.return_value = doc_mock

    with patch.object(setup_mod, "frappe", frappe_mock):
        assert setup_mod.ensure_parent("Expenses - AB", "Test Co", "Expense", "Profit and Loss")
        assert setup_mod.ensure_parent("Expenses - AB", "Test Co", "Expense", "Profit and Loss")

    # insert should be called only once when parent doesn't exist
    assert doc_mock.insert.call_count == 1
    assert frappe_mock.db.set_value.call_count == 0


def test_ensure_parent_updates_existing_metadata():
    frappe_mock = MagicMock()
    frappe_mock.db.exists.return_value = True

    doc_mock = MagicMock()
    doc_mock.root_type = "Asset"
    doc_mock.report_type = "Balance Sheet"
    frappe_mock.get_doc.return_value = doc_mock

    logger_mock = MagicMock()
    frappe_mock.logger.return_value = logger_mock

    with patch.object(setup_mod, "frappe", frappe_mock):
        assert setup_mod.ensure_parent("Expenses - AB", "Test Co", "Expense", "Profit and Loss")

    frappe_mock.db.set_value.assert_called_with(
        "Account",
        "Expenses - AB",
        {"root_type": "Expense", "report_type": "Profit and Loss"},
        update_modified=False,
    )
    logger_mock.warning.assert_called_once()
