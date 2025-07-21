frappe.ui.form.on('Payroll Indonesia Settings', {
    refresh: function(frm) {
        if (!frm.doc.gl_account_mappings?.length) {
            frm.add_custom_button(__('Load Default GL Accounts'), async function() {
                await frappe.call({
                    method: 'payroll_indonesia.payroll_indonesia.doctype.payroll_indonesia_settings.payroll_indonesia_settings.migrate_json_to_child_table'
                });
                await frm.reload_doc();
            }, __('Actions'));
        }
    }
});

