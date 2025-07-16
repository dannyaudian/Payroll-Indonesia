import pytest

frappe = pytest.importorskip("frappe")
from payroll_indonesia.config import config


def test_bpjs_employer_flag_removed():
    config.reset_config_cache()
    cfg = config.get_config()
    tax_cfg = cfg.get("tax_component_config", {})
    assert "bpjs_employer_as_income" not in tax_cfg
    assert tax_cfg.get("bpjs_employee_as_deduction") is True
