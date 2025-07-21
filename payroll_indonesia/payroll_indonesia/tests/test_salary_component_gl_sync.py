import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.config.gl_account_mapper import map_salary_component_to_gl
from payroll_indonesia.config.gl_mapper_core import get_account_mapping_from_defaults
from payroll_indonesia.config.config import get_config as get_default_config


class TestSalaryComponentGLSync(unittest.TestCase):
    def setUp(self):
        self.company = frappe.defaults.get_user_default("Company")
        self.mapping = get_account_mapping_from_defaults()

    def tearDown(self):
        frappe.db.rollback()

    def ensure_component(self, name, comp_type="Earning"):
        if not frappe.db.exists("Salary Component", name):
            doc = frappe.get_doc({
                "doctype": "Salary Component",
                "salary_component": name,
                "type": comp_type,
            })
            doc.insert(ignore_permissions=True)

    def test_mapping_creates_account_row(self):
        component = "Gaji Pokok"
        self.ensure_component(component)
        frappe.db.delete("Salary Component Account", {"parent": component, "company": self.company})

        defaults = get_default_config()
        mapped = map_salary_component_to_gl(self.company, defaults)
        self.assertIn(component, mapped)

        account_name = self.mapping.get(component)
        self.assertIsNotNone(account_name)
        abbr = frappe.get_cached_value("Company", self.company, "abbr")
        full_name = f"{account_name} - {abbr}"

        row = frappe.get_value(
            "Salary Component Account",
            {"parent": component, "company": self.company},
            "default_account",
        )
        self.assertEqual(row, full_name)
        self.assertTrue(frappe.db.exists("Account", full_name))

        # Idempotency
        before = frappe.get_all(
            "Salary Component Account",
            filters={"parent": component, "company": self.company},
        )
        map_salary_component_to_gl(self.company, defaults)
        after = frappe.get_all(
            "Salary Component Account",
            filters={"parent": component, "company": self.company},
        )
        self.assertEqual(len(before), len(after))

    def test_unmapped_component_logs_warning(self, monkeypatch):
        component = "Komisi Spesial"
        self.ensure_component(component)

        import types
        import payroll_indonesia.config.gl_account_mapper as mapper

        logs = []
        monkeypatch.setattr(
            mapper,
            "logger",
            types.SimpleNamespace(
                info=lambda *a, **k: None,
                warning=lambda msg: logs.append(msg),
                debug=lambda *a, **k: None,
                exception=lambda *a, **k: None,
            ),
        )
        errors = []
        monkeypatch.setattr(mapper.frappe, "log_error", lambda msg, title=None: errors.append(msg))

        defaults = get_default_config()
        mapped = map_salary_component_to_gl(self.company, defaults)

        self.assertNotIn(component, mapped)
        self.assertTrue(logs)
        self.assertTrue(errors)
