# -*- coding: utf-8 -*-
import unittest
import pytest

frappe = pytest.importorskip("frappe")

from ...bpjs_payment_summary_detail import bpjs_payment_summary_detail as detail


class TestBPJSPaymentSummaryDetail(unittest.TestCase):
    def test_negative_amount_validation(self):
        doc = frappe.get_doc({
            "doctype": "BPJS Payment Summary Detail",
            "employee": "EMP-TEST",
            "amount": -1000,
        })
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

