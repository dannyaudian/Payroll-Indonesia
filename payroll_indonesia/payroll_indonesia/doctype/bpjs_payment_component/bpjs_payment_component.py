# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 09:27:47 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
import logging

# Set up logger
logger = logging.getLogger(__name__)

class BPJSPaymentComponent(Document):
    def validate(self):
        """Validate component data"""
        # Validate amount
        if not self.amount or self.amount <= 0:
            frappe.throw(_("Amount must be greater than 0"))
            
        # Define valid components and their component types
        component_mapping = {
            "BPJS Kesehatan": "Kesehatan",
            "BPJS JHT": "JHT",
            "BPJS JP": "JP",
            "BPJS JKK": "JKK",
            "BPJS JKM": "JKM",
            "Lainnya": None  # No specific component type for "Other"
        }
        
        # Validate component
        valid_components = list(component_mapping.keys())
        if self.component not in valid_components:
            frappe.throw(_("Component must be one of: {0}").format(", ".join(valid_components)))
        
        # Set the component_type automatically based on component
        derived_type = component_mapping.get(self.component)
        if derived_type:
            # Auto-set component_type based on selected component
            if self.component_type != derived_type:
                self.component_type = derived_type
                logger.info(f"Auto-set component_type to {derived_type} based on component {self.component}")
        elif self.component == "Lainnya" and not self.component_type:
            # For "Other" component, a component_type must be specified
            frappe.throw(_("Component Type must be specified for 'Other' component"))
            
        # Set employer component flag based on component type
        self.set_employer_flag()
    
    def set_employer_flag(self):
        """Set is_employer_component flag based on component type"""
        # JKK and JKM are always employer components
        if self.component_type in ["JKK", "JKM"]:
            self.is_employer_component = 1
        # For others, keep the value as set by the user or default to 0
        elif not hasattr(self, "is_employer_component") or self.is_employer_component is None:
            self.is_employer_component = 0


def get_bpjs_account_mapping(company):
    """
    Get BPJS Account Mapping for this company
    
    Args:
        company (str): Company name
        
    Returns:
        Document: BPJS Account Mapping document or None if not found
    """
    try:
        mapping = frappe.get_all("BPJS Account Mapping", filters={"company": company}, limit=1)

        if mapping:
            return frappe.get_doc("BPJS Account Mapping", mapping[0].name)

        return None
    except Exception as e:
        logger.error(f"Error getting BPJS Account Mapping for company {company}: {str(e)}")
        frappe.log_error(
            f"Error getting BPJS Account Mapping for company {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Account Mapping Error",
        )
        return None