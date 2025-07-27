import sys
from unittest.mock import MagicMock, patch

# Mock frappe before importing the module
frappe_mock = MagicMock()
frappe_utils_mock = MagicMock(flt=lambda x: float(x))
sys.modules.setdefault("frappe", frappe_mock)
sys.modules.setdefault("frappe.utils", frappe_utils_mock)

from payroll_indonesia.config import pph21_ter_december as dec


def test_get_tax_slabs_returns_defaults_when_doc_missing():
    frappe_mock = MagicMock()
    frappe_mock.get_cached_doc.side_effect = Exception("Missing")
    frappe_mock.logger.return_value = MagicMock()

    with patch.object(dec, "frappe", frappe_mock), patch.object(dec.config, "get_value", return_value="x"):
        assert dec.get_tax_slabs() == dec.DEFAULT_TAX_SLABS


def test_get_tax_slabs_parse_document():
    frappe_mock = MagicMock()
    slab_rows = [
        MagicMock(to_amount=1000, percent_deduction=10),
        MagicMock(to_amount=0, percent_deduction=20),
    ]
    slab_doc = MagicMock()
    slab_doc.get.return_value = slab_rows
    frappe_mock.get_cached_doc.return_value = slab_doc

    with patch.object(dec, "frappe", frappe_mock), patch.object(dec.config, "get_value", return_value="x"):
        assert dec.get_tax_slabs() == [(1000.0, 10.0), (float("inf"), 20.0)]
