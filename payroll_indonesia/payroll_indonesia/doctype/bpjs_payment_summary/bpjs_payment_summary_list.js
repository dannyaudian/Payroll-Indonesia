// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-07-02 16:06:24 by dannyaudian

frappe.listview_settings['BPJS Payment Summary'] = {
    add_fields: ['status', 'total', 'payment_entry', 'journal_entry', 'docstatus'],
    
    get_indicator: function(doc) {
        if (doc.docstatus === 0) {
            return [__('Draft'), 'red', 'docstatus,=,0'];
        } 
        
        if (doc.docstatus === 1) {
            if (doc.payment_entry && doc.journal_entry) {
                return [__('Completed'), 'green', 'status,=,Paid'];
            } else if (doc.payment_entry) {
                return [__('Paid'), 'blue', 'status,=,Paid'];
            } else {
                return [__('Submitted'), 'orange', 'docstatus,=,1|status,=,Submitted'];
            }
        } 
        
        if (doc.docstatus === 2) {
            return [__('Cancelled'), 'grey', 'docstatus,=,2'];
        }
        
        return [__('Unknown'), 'red', ''];
    },
    
    formatters: {
        total: (value) => frappe.format_currency(value),
        
        payment_entry: (value) => {
            if (!value) return '';
            return `<a href="/app/payment-entry/${encodeURIComponent(value)}">${value}</a>`;
        },
        
        journal_entry: (value) => {
            if (!value) return '';
            return `<a href="/app/journal-entry/${encodeURIComponent(value)}">${value}</a>`;
        }
    },
    
    onload: function(listview) {
        listview.page.add_action_item(__('Create Payment Entry'), () => {
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
            
            frappe.confirm(
                __('Create Payment Entry for BPJS Payment Summary: {0}?', [doc.name]),
                () => {
                    frappe.show_progress(__('Creating Payment Entry...'), 0.5, 1);
                    
                    frappe.call({
                        method: 'payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.generate_payment_entry',
                        args: {
                            doc: doc.name
                        },
                        callback: (response) => {
                            frappe.hide_progress();
                            
                            if (response.message && response.message.success) {
                                frappe.show_alert({
                                    message: __('Payment Entry {0} created successfully', [response.message.name]),
                                    indicator: 'green'
                                }, 5);
                                
                                listview.refresh();
                                frappe.set_route('Form', 'Payment Entry', response.message.name);
                            } else {
                                frappe.msgprint(__(response.message ? response.message.message : 'Error creating Payment Entry'));
                            }
                        }
                    });
                }
            );
        });
        
        listview.page.add_action_item(__('View Employer Journal'), () => {
            const selected = listview.get_checked_items();
            
            if (selected.length === 0) {
                frappe.msgprint(__('Please select a BPJS Payment Summary'));
                return;
            }
            
            if (selected.length > 1) {
                frappe.msgprint(__('Please select only one BPJS Payment Summary at a time'));
                return;
            }
            
            const doc = selected[0];
            
            if (!doc.journal_entry) {
                frappe.msgprint(__('No Journal Entry exists for this BPJS Payment Summary'));
                return;
            }
            
            frappe.set_route('Form', 'Journal Entry', doc.journal_entry);
        });
    }
};
