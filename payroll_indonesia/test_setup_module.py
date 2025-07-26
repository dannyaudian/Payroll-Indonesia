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
    frappe_mock.get_doc.return_value = doc_mock

    with patch.object(setup_mod, "frappe", frappe_mock):
        assert setup_mod.ensure_parent("Expenses - AB", "Test Co", "Expense", "Profit and Loss")
        assert setup_mod.ensure_parent("Expenses - AB", "Test Co", "Expense", "Profit and Loss")

    # insert should be called only once when parent doesn't exist
    assert doc_mock.insert.call_count == 1
