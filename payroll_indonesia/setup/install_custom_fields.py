# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Script to programmatically install custom fields for Payroll Indonesia.
This approach avoids issues with fixture syncing.
"""

import json
import os

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint

from payroll_indonesia.frappe_helpers import logger


def install_custom_fields():
    """Install custom fields for Payroll Indonesia"""
    try:
        # Attempt to load custom fields from JSON file
        app_path = frappe.get_app_path("payroll_indonesia")
        fixture_path = os.path.join(app_path, "payroll_indonesia", "fixtures", "custom_fields.json")

        if not os.path.exists(fixture_path):
            logger.warning(f"Custom fields fixture not found at {fixture_path}")
            return

        with open(fixture_path, "r") as f:
            fields_data = json.load(f)

        if not fields_data:
            logger.warning("No custom fields found in fixture file")
            return

        # Group fields by doctype
        fields_by_doctype = {}
        for field in fields_data:
            dt = field.get("dt")
            if not dt:
                continue

            if dt not in fields_by_doctype:
                fields_by_doctype[dt] = []

            # Clean up the field definition
            field_def = {k: v for k, v in field.items() if k not in ["doctype", "name"]}
            fields_by_doctype[dt].append(field_def)

        # Install custom fields for each doctype
        for dt, fields in fields_by_doctype.items():
            if fields:
                logger.info(f"Installing {len(fields)} custom fields for {dt}")
                create_custom_fields({dt: fields}, update=True)

        logger.info("Custom field installation complete")

    except Exception as e:
        logger.exception(f"Error installing custom fields: {e}")
