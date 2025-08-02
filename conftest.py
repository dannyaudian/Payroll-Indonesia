import sys
import types
import datetime

frappe = types.ModuleType("frappe")

class DummyLogger:
    def info(self, *args, **kwargs):
        pass
    def warning(self, *args, **kwargs):
        pass
    def error(self, *args, **kwargs):
        pass
    def debug(self, *args, **kwargs):
        pass

frappe.logger = lambda *a, **k: DummyLogger()
frappe.get_doc = lambda *a, **k: {}
frappe.throw = lambda *a, **k: None
frappe.ValidationError = type("ValidationError", (Exception,), {})
frappe.LinkValidationError = type("LinkValidationError", (Exception,), {})
frappe.log_error = lambda *a, **k: None
frappe.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
frappe.new_doc = lambda *a, **k: types.SimpleNamespace(
    set=lambda self, name, value: setattr(self, name, value),
    append=lambda *a, **k: types.SimpleNamespace(set=lambda *a, **k: None),
    is_new=lambda: True,
    save=lambda *a, **k: None,
    get=lambda *a, **k: None,
    monthly_details=[],
)
frappe.get_hooks = lambda *a, **k: {}
frappe.get_attr = lambda path: None

utils = types.ModuleType("frappe.utils")
utils.flt = lambda val, precision=None: float(val)
utils.getdate = lambda val: datetime.datetime.strptime(str(val), "%Y-%m-%d")
utils.now = lambda: "2024-01-01 00:00:00"

safe_exec_mod = types.ModuleType("frappe.utils.safe_exec")
safe_exec_mod.safe_eval = lambda expr, context=None: eval(expr, context or {})

frappe.utils = utils
frappe.session = types.SimpleNamespace(user="test")

sys.modules.setdefault("frappe", frappe)
sys.modules.setdefault("frappe.utils", utils)
sys.modules.setdefault("frappe.utils.safe_exec", safe_exec_mod)
model_mod = types.ModuleType("frappe.model")
document_mod = types.ModuleType("frappe.model.document")
document_mod.Document = type("Document", (object,), {})
model_mod.document = document_mod
sys.modules.setdefault("frappe.model", model_mod)
sys.modules.setdefault("frappe.model.document", document_mod)
payroll_entry_mod = types.ModuleType("hrms.payroll.doctype.payroll_entry.payroll_entry")
payroll_entry_mod.PayrollEntry = type("PayrollEntry", (object,), {})
sys.modules.setdefault("hrms.payroll.doctype.payroll_entry.payroll_entry", payroll_entry_mod)
