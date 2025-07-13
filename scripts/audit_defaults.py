from __future__ import annotations

import json
from pathlib import Path
import sys

REQUIRED_KEYS = ["ptkp", "ptkp_to_ter_mapping", "tax_brackets", "tipe_karyawan"]


def load_defaults(path: str | Path) -> dict:
    """Load defaults.json from the given path."""
    with Path(path).open() as f:
        return json.load(f)


def validate_defaults(data: dict) -> list[str]:
    """Return a list of validation errors."""
    errors: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in data:
            errors.append(f"Missing required key: {key}")

    ptkp = data.get("ptkp", {})
    if not isinstance(ptkp, dict):
        errors.append("ptkp must be a dictionary")
    else:
        for code, value in ptkp.items():
            if not isinstance(code, str):
                errors.append(f"ptkp key {code!r} is not a string")
            if not isinstance(value, (int, float)):
                errors.append(f"ptkp value for {code} is not a number")

    mapping = data.get("ptkp_to_ter_mapping", {})
    if not isinstance(mapping, dict):
        errors.append("ptkp_to_ter_mapping must be a dictionary")
    else:
        for code, ter in mapping.items():
            if code not in ptkp:
                errors.append(f"ptkp_to_ter_mapping key {code} not found in ptkp")
            if not isinstance(ter, str):
                errors.append(f"ptkp_to_ter_mapping value for {code} is not a string")

    brackets = data.get("tax_brackets", [])
    if not isinstance(brackets, list):
        errors.append("tax_brackets must be a list")
    else:
        required = {"income_from", "income_to", "tax_rate"}
        for i, row in enumerate(brackets, 1):
            if not isinstance(row, dict):
                errors.append(f"tax_brackets row {i} is not a dict")
                continue
            missing = required - row.keys()
            if missing:
                errors.append(
                    f"tax_brackets row {i} missing fields: {', '.join(sorted(missing))}"
                )
            for field in required:
                if field in row and not isinstance(row[field], (int, float)):
                    errors.append(
                        f"tax_brackets row {i} field {field} is not a number"
                    )

    tipe = data.get("tipe_karyawan", [])
    if not isinstance(tipe, list):
        errors.append("tipe_karyawan must be a list")
    else:
        for t in tipe:
            if not isinstance(t, str):
                errors.append(f"tipe_karyawan value {t!r} is not a string")

    return errors


def main(path: str = "payroll_indonesia/config/defaults.json") -> None:
    """Audit a defaults.json file and print results."""
    data = load_defaults(path)
    errors = validate_defaults(data)

    if errors:
        print("Audit failed:")
        for err in errors:
            print(f"- {err}")
        sys.exit(1)

    print(f"All checks passed for {path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Audit defaults.json")
    parser.add_argument(
        "--path",
        default="payroll_indonesia/config/defaults.json",
        help="Path to defaults.json",
    )
    args = parser.parse_args()
    main(args.path)
