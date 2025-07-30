import sys
import os
import types
import importlib

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Minimal frappe stub with db and get_value support
frappe = types.ModuleType("frappe")
utils_mod = types.ModuleType("frappe.utils")


def flt(val, precision=None):
    return float(val or 0)


utils_mod.flt = flt


class ValidationError(Exception):
    pass


class DummyDB:
    def __init__(self):
        self.records = {}
        self.ter_records = {}

    def exists(self, doctype, filters):
        if doctype == "PTKP Table":
            tax_status = filters.get("tax_status")
            return tax_status in self.records
        if doctype == "TER Mapping Table":
            tax_status = filters.get("tax_status")
            return tax_status in self.ter_records
        return False

dummy_db = DummyDB()


def get_value(doctype, filters, fields, as_dict=False):
    if doctype == "PTKP Table":
        tax_status = filters.get("tax_status")
        if tax_status in dummy_db.records:
            record = dummy_db.records[tax_status]
            field = fields[0] if isinstance(fields, (list, tuple)) else fields
            if as_dict:
                return {field: record.get(field)}
            return record.get(field)
    if doctype == "TER Mapping Table":
        tax_status = filters.get("tax_status")
        if tax_status in dummy_db.ter_records:
            record = dummy_db.ter_records[tax_status]
            field = fields[0] if isinstance(fields, (list, tuple)) else fields
            if as_dict:
                return {field: record.get(field)}
            return record.get(field)
    return None


class DummyLogger:
    def __init__(self):
        self.warning_messages = []
        self.info_messages = []

    def info(self, msg):
        self.info_messages.append(msg)

    def warning(self, msg):
        self.warning_messages.append(msg)

dummy_logger = DummyLogger()


def logger():
    return dummy_logger


frappe.utils = utils_mod
frappe.logger = logger
frappe.ValidationError = ValidationError
frappe.db = dummy_db
frappe.get_value = get_value

sys.modules.setdefault("frappe", frappe)
sys.modules.setdefault("frappe.utils", utils_mod)

# Import module after stubbing frappe
config = importlib.import_module("payroll_indonesia.config.config")


def test_get_ptkp_amount_from_tax_status_found():
    frappe.db.records = {"TK0": {"ptkp_amount": 54000000}}
    assert config.get_ptkp_amount_from_tax_status("TK0") == 54000000.0


def test_get_ptkp_amount_from_tax_status_missing_field():
    frappe.db.records = {"TK0": {}}
    dummy_logger.warning_messages.clear()
    assert config.get_ptkp_amount_from_tax_status("TK0") == 0.0
    assert any(
        "No ptkp_amount" in msg for msg in dummy_logger.warning_messages
    )


def test_get_ptkp_and_ter_code_with_dict():
    frappe.db.records = {"TK0": {"ptkp_amount": 54000000}}
    frappe.db.ter_records = {"TK0": {"ter_code": "A"}}
    employee = {"tax_status": "TK0"}
    assert config.get_ptkp_amount(employee) == 54000000.0
    assert config.get_ter_code(employee) == "A"


def test_get_ptkp_and_ter_code_with_object():
    frappe.db.records = {"TK0": {"ptkp_amount": 54000000}}
    frappe.db.ter_records = {"TK0": {"ter_code": "A"}}

    class Emp:
        def __init__(self, tax_status):
            self.tax_status = tax_status

    employee = Emp("TK0")
    assert config.get_ptkp_amount(employee) == 54000000.0
    assert config.get_ter_code(employee) == "A"
