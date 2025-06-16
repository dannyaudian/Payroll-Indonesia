// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-06-16 09:21:29 by dannyaudian

frappe.ui.form.on('BPJS Account Mapping', {
    refresh: function(frm) {
        // Add button to view BPJS Settings
        frm.add_custom_button(__('View BPJS Settings'), async function() {
            frappe.set_route('Form', 'BPJS Settings');
        }, __('Actions'));
        
        // Add button to test journal entry if document is saved
        if (!frm.is_new()) {
            frm.add_custom_button(__('Test Journal Entry'), async function() {
                await validate_create_journal_entry(frm);
            }, __('Actions'));
        }
        
        // Add button to open BPJS Payment Summary if exists
        if (!frm.is_new()) {
            frm.add_custom_button(__('BPJS Payment Summaries'), async function() {
                frappe.set_route('List', 'BPJS Payment Summary', {
                    'company': frm.doc.company
                });
            }, __('View'));
        }
        
        // Add indicator if all accounts are filled
        update_mapping_status(frm);
    },
    
    company: function(frm) {
        // Reset fields when company changes
        [
            'kesehatan_employee_account', 
            'kesehatan_employer_debit_account',
            'kesehatan_employer_credit_account', 
            'jht_employee_account',
            'jht_employer_debit_account', 
            'jht_employer_credit_account',
            'jp_employee_account', 
            'jp_employer_debit_account',
            'jp_employer_credit_account', 
            'jkk_employer_debit_account',
            'jkk_employer_credit_account', 
            'jkm_employer_debit_account',
            'jkm_employer_credit_account'
        ].forEach(function(field) {
            frm.set_value(field, '');
        });
    }
});

// Validate and test journal entry creation
async function validate_create_journal_entry(frm) {
    const values = await new Promise(resolve => {
        frappe.prompt([
            {
                fieldtype: 'Link',
                label: __('BPJS Payment Component'),
                fieldname: 'bpjs_component',
                options: 'BPJS Payment Component',
                reqd: 1,
                get_query: function() {
                    return {
                        filters: {
                            'docstatus': 1,
                            'company': frm.doc.company
                        }
                    };
                }
            }
        ], values => resolve(values), __('Select BPJS Component for Test'), __('Create Test Entry'));
    });
    
    try {
        const result = await frappe.call({
            method: 'payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.test_create_journal_entry',
            args: {
                mapping_name: frm.doc.name,
                bpjs_component: values.bpjs_component
            }
        });
        
        if (result.message) {
            frappe.show_warning(__('Test Journal Entry created successfully. Entry ID: {0}', [result.message]));
        } else {
            frappe.show_warning(__('Failed to create test Journal Entry. Check console for details.'));
        }
    } catch (error) {
        frappe.show_warning(__('Error creating test Journal Entry: {0}', [error.message || error]));
        console.error("Error in test journal entry creation:", error);
    }
}

// Update status indicator based on mapping completeness
function update_mapping_status(frm) {
    const required_accounts = [
        'kesehatan_employee_account', 
        'kesehatan_employer_debit_account',
        'kesehatan_employer_credit_account',
        'jht_employee_account',
        'jht_employer_debit_account',
        'jht_employer_credit_account'
    ];
    
    let total_filled = 0;
    required_accounts.forEach(function(field) {
        if (frm.doc[field]) {
            total_filled++;
        }
    });
    
    const percentage = Math.round((total_filled / required_accounts.length) * 100);
    
    if (percentage == 100) {
        frm.dashboard.set_headline(
            __('All required accounts are set ({0}%)', [percentage]),
            'green'
        );
    } else if (percentage >= 50) {
        frm.dashboard.set_headline(
            __('Some required accounts are missing ({0}%)', [percentage]),
            'orange'
        );
    } else {
        frm.dashboard.set_headline(
            __('Many required accounts are missing ({0}%)', [percentage]),
            'red'
        );
    }
}