frappe.ui.form.on('Employee', {
    refresh: function(frm) {
        // Add custom buttons or functionality here
        
        // Add button to verify employee tax settings
        frm.add_custom_button(__('Verify Tax Settings'), function() {
            frappe.call({
                method: 'payroll_indonesia.api.verify_employee_tax_settings',
                args: {
                    employee: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        const result = r.message;
                        
                        if (result.status === 'success') {
                            frappe.msgprint({
                                title: __('Tax Settings Verification'),
                                indicator: 'green',
                                message: __('All tax settings are properly configured.')
                            });
                        } else {
                            let message = __('The following tax settings need attention:') + '<ul>';
                            
                            if (result.issues && result.issues.length) {
                                result.issues.forEach(issue => {
                                    message += `<li>${issue}</li>`;
                                });
                            }
                            
                            message += '</ul>';
                            
                            frappe.msgprint({
                                title: __('Tax Settings Issues'),
                                indicator: 'orange',
                                message: message
                            });
                        }
                    }
                }
            });
        }, __('Actions'));
    },
    
    status_pajak: function(frm) {
        // Update jumlah_tanggungan based on status_pajak
        if (frm.doc.status_pajak) {
            var status = frm.doc.status_pajak;
            if (status && status.length >= 2) {
                var tanggungan = parseInt(status.charAt(status.length - 1));
                frm.set_value('jumlah_tanggungan', tanggungan);
            }
        }
        
        // Show TER category information
        if (frm.doc.status_pajak) {
            frappe.call({
                method: 'payroll_indonesia.api.get_ter_category_for_status',
                args: {
                    tax_status: frm.doc.status_pajak
                },
                callback: function(r) {
                    if (r.message && r.message.ter_category) {
                        frappe.show_alert({
                            message: __('TER Category: {0}', [r.message.ter_category]),
                            indicator: 'blue'
                        }, 10);
                    }
                }
            });
        }
    }
});