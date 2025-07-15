# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Schema definitions for custom fields used in Payroll Indonesia.
Provides centralized documentation and validation for custom fields.
"""

from typing import Dict, Any, List, Optional, Union


class CustomFieldSchema:
    """Base schema class for custom fields"""

    @classmethod
    def validate(cls, doc, field_name, value):
        """Validate a field value against schema"""
        if field_name not in cls.FIELDS:
            return False, f"Field {field_name} not defined in schema"

        field_spec = cls.FIELDS[field_name]

        # Check type
        expected_type = field_spec.get("type")
        if expected_type == "str" and not isinstance(value, str):
            return False, f"Field {field_name} must be a string"
        elif expected_type == "int" and not isinstance(value, int):
            return False, f"Field {field_name} must be an integer"
        elif expected_type == "float" and not isinstance(value, (int, float)):
            return False, f"Field {field_name} must be a number"
        elif expected_type == "bool" and not isinstance(value, bool):
            if not isinstance(value, int) or value not in (0, 1):
                return False, f"Field {field_name} must be a boolean"

        # Check options/enum
        if "options" in field_spec and value not in field_spec["options"]:
            return False, f"Field {field_name} must be one of: {', '.join(field_spec['options'])}"

        return True, None

    @classmethod
    def get_default(cls, field_name):
        """Get default value for a field"""
        if field_name in cls.FIELDS:
            return cls.FIELDS[field_name].get("default")
        return None


class SalarySlipSchema(CustomFieldSchema):
    """Schema for Salary Slip custom fields"""

    FIELDS = {
        "status_pajak": {
            "type": "str",
            "required": True,
            "options": [
                "TK0",
                "TK1",
                "TK2",
                "TK3",
                "K0",
                "K1",
                "K2",
                "K3",
                "HB0",
                "HB1",
                "HB2",
                "HB3",
            ],
            "default": "TK0",
            "description": "Tax status code for PTKP calculation",
        },
        "tax_method": {
            "type": "str",
            "required": True,
            "options": ["Progressive", "TER"],
            "default": "Progressive",
            "description": "Tax calculation method",
        },
        "is_using_ter": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag indicating TER method is being used",
        },
        "ter_category": {
            "type": "str",
            "required": False,
            "options": ["TER A", "TER B", "TER C"],
            "description": "TER category based on tax status",
        },
        "ter_rate": {"type": "float", "required": False, "description": "TER rate percentage"},
        "monthly_gross_for_ter": {
            "type": "float",
            "required": False,
            "description": "Monthly gross amount used for TER calculation",
        },
        "annual_taxable_income": {
            "type": "float",
            "required": False,
            "description": "Annualized taxable income",
        },
        "koreksi_pph21": {
            "type": "float",
            "required": False,
            "description": "PPh 21 correction amount for December",
        },
        "is_final_gabung_suami": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag indicating joint NPWP with spouse",
        },
        "biaya_jabatan": {
            "type": "float",
            "required": False,
            "description": "Occupation allowance deduction",
        },
        "netto": {"type": "float", "required": False, "description": "Net taxable income"},
        "total_bpjs": {"type": "float", "required": False, "description": "Total BPJS deductions"},
        "ytd_gross_pay": {
            "type": "float",
            "required": False,
            "description": "Year-to-date gross pay",
        },
        "ytd_bpjs": {
            "type": "float",
            "required": False,
            "description": "Year-to-date BPJS deductions",
        },
        "ytd_pph21": {"type": "float", "required": False, "description": "Year-to-date PPh 21 tax"},
        "ytd_taxable_components": {
            "type": "float",
            "required": False,
            "description": "Year-to-date taxable components",
        },
        "ytd_tax_deductions": {
            "type": "float",
            "required": False,
            "description": "Year-to-date tax deductions",
        },
        "is_december_override": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag indicating December override for tax calculation",
        },
        "kesehatan_employee": {
            "type": "float",
            "required": False,
            "description": "BPJS Kesehatan employee contribution",
        },
        "jht_employee": {
            "type": "float",
            "required": False,
            "description": "BPJS JHT employee contribution",
        },
        "jp_employee": {
            "type": "float",
            "required": False,
            "description": "BPJS JP employee contribution",
        },
        "kesehatan_employer": {
            "type": "float",
            "required": False,
            "description": "BPJS Kesehatan employer contribution",
        },
        "jht_employer": {
            "type": "float",
            "required": False,
            "description": "BPJS JHT employer contribution",
        },
        "jp_employer": {
            "type": "float",
            "required": False,
            "description": "BPJS JP employer contribution",
        },
        "jkk_employer": {
            "type": "float",
            "required": False,
            "description": "BPJS JKK employer contribution",
        },
        "jkm_employer": {
            "type": "float",
            "required": False,
            "description": "BPJS JKM employer contribution",
        },
        "total_bpjs_employer": {
            "type": "float",
            "required": False,
            "description": "Total BPJS employer contributions",
        },
        "tax_components_json": {
            "type": "str",
            "required": False,
            "description": "JSON string of tax components data",
        },
        "tax_brackets_json": {
            "type": "str",
            "required": False,
            "description": "JSON string of tax brackets details",
        },
        "payroll_note": {
            "type": "str",
            "required": False,
            "description": "Payroll processing notes",
        },
        # Fields referenced in code but not in custom_fields.json
        "ptkp_value": {
            "type": "float",
            "required": False,
            "description": "PTKP value for tax calculation",
        },
        "monthly_taxable": {
            "type": "float",
            "required": False,
            "description": "Monthly taxable income amount",
        },
        "tax_deductions": {
            "type": "float",
            "required": False,
            "description": "Tax deduction amount",
        },
        "annual_pkp": {
            "type": "float",
            "required": False,
            "description": "Annual PKP (taxable income after deductions)",
        },
        "annual_tax": {"type": "float", "required": False, "description": "Annual tax amount"},
        "december_tax": {"type": "float", "required": False, "description": "December tax amount"},
        "indo_base_gross_pay": {
            "type": "float",
            "required": False,
            "description": "Base gross pay amount",
        },
        "indo_base_net_pay": {
            "type": "float",
            "required": False,
            "description": "Base net pay amount",
        },
        "indo_base_total_deduction": {
            "type": "float",
            "required": False,
            "description": "Base total deduction amount",
        },
        "salary_year": {"type": "int", "required": False, "description": "Salary year"},
        "salary_month": {"type": "int", "required": False, "description": "Salary month"},
        "is_december_slip": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag indicating December slip",
        },
        "monthly_taxable_income": {
            "type": "float",
            "required": False,
            "description": "Monthly taxable income amount",
        },
        "monthly_tax": {"type": "float", "required": False, "description": "Monthly tax amount"},
        "taxable_earnings": {
            "type": "float",
            "required": False,
            "description": "Taxable earnings amount",
        },
    }


class PayrollEntrySchema(CustomFieldSchema):
    """Schema for Payroll Entry custom fields"""

    FIELDS = {
        "ter_method_enabled": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag to enable TER method for tax calculation",
        },
        "is_december_override": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag to process as December for year-end adjustments",
        },
        "calculate_indonesia_tax": {
            "type": "bool",
            "required": False,
            "default": True,
            "description": "Flag to enable Indonesia tax calculations",
        },
        "tax_method": {
            "type": "str",
            "required": False,
            "options": ["Progressive", "TER"],
            "default": "Progressive",
            "description": "Tax calculation method",
        },
    }


class EmployeeSchema(CustomFieldSchema):
    """Schema for Employee custom fields"""

    FIELDS = {
        "status_pajak": {
            "type": "str",
            "required": False,
            "options": [
                "TK0",
                "TK1",
                "TK2",
                "TK3",
                "K0",
                "K1",
                "K2",
                "K3",
                "HB0",
                "HB1",
                "HB2",
                "HB3",
            ],
            "default": "TK0",
            "description": "Tax status code for PTKP calculation",
        },
        "golongan": {"type": "str", "required": False, "description": "Employee grade/rank"},
        "jabatan": {"type": "str", "required": False, "description": "Employee position/title"},
        "jumlah_tanggungan": {
            "type": "int",
            "required": False,
            "default": 0,
            "description": "Number of dependents",
        },
        "override_tax_method": {
            "type": "str",
            "required": False,
            "options": ["", "Progressive", "TER"],
            "default": "",
            "description": "Override tax calculation method",
        },
        "tipe_karyawan": {
            "type": "str",
            "required": False,
            "options": ["Tetap", "Tidak Tetap", "Freelance"],
            "description": "Employee type",
        },
        "penghasilan_final": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag for final income tax",
        },
        "npwp": {"type": "str", "required": False, "description": "Tax ID number"},
        "ktp": {"type": "str", "required": False, "description": "ID card number"},
        "npwp_suami": {"type": "str", "required": False, "description": "Husband's tax ID number"},
        "npwp_gabung_suami": {
            "type": "bool",
            "required": False,
            "default": False,
            "description": "Flag for joint tax ID with husband",
        },
        "ikut_bpjs_kesehatan": {
            "type": "bool",
            "required": False,
            "default": True,
            "description": "Flag for BPJS Health participation",
        },
        "bpjs_kesehatan_id": {"type": "str", "required": False, "description": "BPJS Health ID"},
        "ikut_bpjs_ketenagakerjaan": {
            "type": "bool",
            "required": False,
            "default": True,
            "description": "Flag for BPJS Employment participation",
        },
        "bpjs_ketenagakerjaan_id": {
            "type": "str",
            "required": False,
            "description": "BPJS Employment ID",
        },
    }
