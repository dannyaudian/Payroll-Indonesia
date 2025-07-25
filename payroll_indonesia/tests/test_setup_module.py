import os
import sys
import importlib
from types import SimpleNamespace


def make_fake_frappe(parents_exist=True):
    created = []
    logs = []

    class DB:
        def exists(self, doctype, name):
            if not parents_exist:
                return False
            return name in {
                "Expenses - TEST",
                "Liabilities - TEST",
                "Duties and Taxes - TEST",
            }

        def commit(self):
            pass

    def get_all(doctype, filters=None, fields=None, pluck=None):
        assert "account_type" not in filters
        if not parents_exist:
            return []
        result = []
        if filters.get("root_type") == "Expense":
            result = ["Expenses - TEST"] if pluck else [SimpleNamespace(name="Expenses - TEST")]
        elif filters.get("root_type") == "Liability":
            result = (
                ["Liabilities - TEST"] if pluck else [SimpleNamespace(name="Liabilities - TEST")]
            )
        return result

    def get_doc(doc):
        class Doc(dict):
            def insert(self, ignore_permissions=False):
                created.append(self)

        return Doc(doc)

    def get_app_path(app, *parts):
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), app)
        return os.path.join(base, *parts)

    def logger():
        class L:
            def info(self, msg):
                logs.append(msg)

            def warning(self, msg):
                logs.append(f"WARNING: {msg}")

        return L()

    fake_frappe = SimpleNamespace(
        db=SimpleNamespace(exists=DB().exists, commit=DB().commit),
        get_all=get_all,
        get_doc=get_doc,
        get_app_path=get_app_path,
        msgprint=lambda m: None,
        log_error=lambda m, t=None: logs.append(m),
        logger=logger,
        ValidationError=Exception,
    )

    return fake_frappe, created, logs


def test_create_default_accounts_no_account_type(monkeypatch):
    fake_frappe, created, logs = make_fake_frappe()
    sys.modules["frappe"] = fake_frappe
    sys.modules["payroll_indonesia.payroll_indonesia.setup.gl_account_mapper"] = SimpleNamespace(
        assign_gl_accounts_to_salary_components=lambda *a, **k: None
    )
    sys.modules["payroll_indonesia.payroll_indonesia.setup.settings_migration"] = SimpleNamespace(
        setup_default_settings=lambda: None
    )
    setup_module = importlib.import_module(
        "payroll_indonesia.payroll_indonesia.setup.setup_module"
    )
    monkeypatch.setattr(setup_module, "frappe", fake_frappe)

    setup_module.create_default_accounts("Test Company", "TEST")

    assert created, "Accounts were not created"


def test_create_default_accounts_skip_when_no_parent(monkeypatch):
    fake_frappe, created, logs = make_fake_frappe(parents_exist=False)
    sys.modules["frappe"] = fake_frappe
    sys.modules["payroll_indonesia.payroll_indonesia.setup.gl_account_mapper"] = SimpleNamespace(
        assign_gl_accounts_to_salary_components=lambda *a, **k: None
    )
    sys.modules["payroll_indonesia.payroll_indonesia.setup.settings_migration"] = SimpleNamespace(
        setup_default_settings=lambda: None
    )
    setup_module = importlib.import_module(
        "payroll_indonesia.payroll_indonesia.setup.setup_module"
    )
    monkeypatch.setattr(setup_module, "frappe", fake_frappe)

    setup_module.create_default_accounts("Test Company", "TEST")

    assert not created, "Accounts should be skipped when no parent is found"
    assert any("Skipping account" in log for log in logs)
