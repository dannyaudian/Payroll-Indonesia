frappe.ui.form.on('Payroll Indonesia Settings', {
    refresh: function(frm) {
        const has_json = frm.doc.expense_accounts_json || frm.doc.payable_accounts_json;
        if (!frm.doc.gl_account_mappings?.length && has_json) {
            frm.add_custom_button(__('Migrate GL Account JSON'), async function() {
                await frappe.call({
                    method: 'payroll_indonesia.payroll_indonesia.doctype.payroll_indonesia_settings.payroll_indonesia_settings.migrate_json_to_child_table'
                });
                await frm.reload_doc();
            }, __('Actions'));
        }
    }
});

