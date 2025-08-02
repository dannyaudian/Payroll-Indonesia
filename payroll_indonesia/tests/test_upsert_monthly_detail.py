import sys
import types


def test_upsert_monthly_detail_handles_error_state(monkeypatch):
    sys.modules['frappe'] = types.SimpleNamespace()
    from payroll_indonesia.utils.sync_annual_payroll_history import upsert_monthly_detail

    class Row:
        def set(self, key, value):
            setattr(self, key, value)

    class HistoryDoc:
        def __init__(self):
            self.monthly_details = []

        def get(self, key, default=None):
            return getattr(self, key, default)

        def append(self, key, value):
            assert key == 'monthly_details'
            row = Row()
            self.monthly_details.append(row)
            return row

    history = HistoryDoc()

    assert upsert_monthly_detail(history, {'bulan': 1, 'error_state': 'oops'})
    assert history.monthly_details[0].error_state == 'oops'

    assert upsert_monthly_detail(history, {'bulan': 1, 'error_state': 'new'})
    assert history.monthly_details[0].error_state == 'new'
