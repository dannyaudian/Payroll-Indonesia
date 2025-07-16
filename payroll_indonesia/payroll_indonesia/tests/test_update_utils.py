import types
import importlib

from payroll_indonesia.utilities import sanitize_update_data


class DummyDoc:
    def __init__(self):
        self.updated = {}

    def db_set(self, key, value):
        if key == "creation":
            raise Exception("CannotChangeConstantError")
        self.updated[key] = value


def test_sanitize_update_data_removes_creation():
    data = {"name": "DOC-1", "creation": "2024-01-01", "value": 1}
    result = sanitize_update_data(data)
    assert "creation" not in result
    assert result["name"] == "DOC-1"
    assert result["value"] == 1


def test_update_with_sanitized_data_does_not_raise():
    doc = DummyDoc()
    update = {"journal_entry": "JE-1", "creation": "2024-01-01"}
    sanitized = sanitize_update_data(update)
    for key, val in sanitized.items():
        doc.db_set(key, val)
    assert doc.updated == {"journal_entry": "JE-1"}
