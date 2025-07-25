import os
import sys
import importlib
from types import SimpleNamespace


def make_fake_frappe():
    created = []
    logs = []

    class DB:
        def exists(self, doctype, name):
            return name in {
                "Expenses - TEST",
                "Liabilities - TEST",
                "Duties and Taxes - TEST",
            }

        def commit(self):
            pass

    def get_all(doctype, filters=None, fields=None):
        assert "account_type" not in filters
        if filters.get("root_type") == "Expense":
            return [SimpleNamespace(name="Expenses - TEST")]
        if filters.get("root_type") == "Liability":
            return [SimpleNamespace(name="Liabilities - TEST")]
        return []

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
    sys.modules[
        "payroll_indonesia.payroll_indonesia.setup.gl_account_mapper"
    ] = SimpleNamespace(assign_gl_accounts_to_salary_components=lambda *a, **k: None)
    sys.modules[
        "payroll_indonesia.payroll_indonesia.setup.settings_migration"
    ] = SimpleNamespace(setup_default_settings=lambda: None)
    setup_module = importlib.import_module(
        "payroll_indonesia.payroll_indonesia.setup.setup_module"
    )
    monkeypatch.setattr(setup_module, "frappe", fake_frappe)

    setup_module.create_default_accounts("Test Company", "TEST")

    assert created, "Accounts were not created"
