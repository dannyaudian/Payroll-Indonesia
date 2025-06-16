// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-06-16 09:36:04 by dannyaudian

frappe.listview_settings['BPJS Payment Summary'] = {
    add_fields: ["status", "total", "payment_entry", "docstatus"],
    
    get_indicator: function(doc) {
        if (doc.docstatus === 0) {
            return [__("Draft"), "red", "docstatus,=,0"];
        } else if (doc.docstatus === 1) {
            if (doc.status === "Paid") {
                return [__("Paid"), "green", "status,=,Paid"];
            } else {
                return [__("Submitted"), "blue", "docstatus,=,1|status,=,Submitted"];
            }
        } else if (doc.docstatus === 2) {
            return [__("Cancelled"), "grey", "docstatus,=,2"];
        }
    },
    
    formatters: {
        total: function(value) {
            return frappe.format_currency(value);
        }
    },
    
    onload: function(listview) {
        listview.page.add_action_item(__('Create Payment Entry'), function() {
            const selected = listview.get_checked_items();
            if (selected.length === 0) {
                frappe.msgprint(__('Please select at least one BPJS Payment Summary'));
                return;
            }
            
            if (selected.length > 1) {
                frappe.msgprint(__('Please select only one BPJS Payment Summary at a time'));
                return;
            }
            
            const doc = selected[0];
            
            if (doc.docstatus !== 1) {
                frappe.msgprint(__('BPJS Payment Summary must be submitted before creating a Payment Entry'));
                return;
            }
            
            if (doc.payment_entry) {
                frappe.msgprint(__('Payment Entry already exists for this BPJS Payment Summary'));
                return;
            }
            
            frappe.set_route('Form', 'BPJS Payment Summary', doc.name);
        });
    }
};