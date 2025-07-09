from dataclasses import dataclass
from frappe.utils import flt

from payroll_indonesia.config.config import get_live_config

__all__ = ["BPJSSettings", "get_bpjs_settings"]


@dataclass
class BPJSSettings:
    kesehatan_employee_percent: float
    kesehatan_employer_percent: float
    kesehatan_max_salary: float
    jht_employee_percent: float
    jht_employer_percent: float
    jp_employee_percent: float
    jp_employer_percent: float
    jp_max_salary: float
    jkk_percent: float
    jkm_percent: float


def get_bpjs_settings() -> BPJSSettings:
    """Return BPJS configuration from live settings or defaults."""
    cfg = get_live_config().get("bpjs", {})
    return BPJSSettings(
        kesehatan_employee_percent=flt(cfg.get("kesehatan_employee_percent", 1.0)),
        kesehatan_employer_percent=flt(cfg.get("kesehatan_employer_percent", 4.0)),
        kesehatan_max_salary=flt(cfg.get("kesehatan_max_salary", 12000000)),
        jht_employee_percent=flt(cfg.get("jht_employee_percent", 2.0)),
        jht_employer_percent=flt(cfg.get("jht_employer_percent", 3.7)),
        jp_employee_percent=flt(cfg.get("jp_employee_percent", 1.0)),
        jp_employer_percent=flt(cfg.get("jp_employer_percent", 2.0)),
        jp_max_salary=flt(cfg.get("jp_max_salary", 9077600)),
        jkk_percent=flt(cfg.get("jkk_percent", 0.24)),
        jkm_percent=flt(cfg.get("jkm_percent", 0.3)),
    )
