// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-07-05 by dannyaudian

frappe.ui.form.on('Payroll Entry', {
    refresh: function(frm) {
        // Tambahkan UI alert untuk periode payroll Indonesia
        if (frm.doc.start_date && frm.doc.end_date) {
            let start_month = moment(frm.doc.start_date).format('MMMM');
            let end_month = moment(frm.doc.end_date).format('MMMM');
            
            if (start_month !== end_month) {
                frm.dashboard.add_indicator(__("Periode harus dalam bulan yang sama untuk perhitungan pajak Indonesia"), "red");
            }
        }
        
        // Show December override indicator if enabled, regardless of actual month
        if (frm.doc.is_december_override) {
            frm.dashboard.add_indicator(__("December Override Active - Akan dilakukan perhitungan koreksi pajak tahunan"), "blue");
        }
        
        // Add toggle button for December Override
        if (frm.doc.calculate_indonesia_tax) {
            frm.add_custom_button(__('Toggle December Override'), function() {
                frm.set_value('is_december_override', frm.doc.is_december_override ? 0 : 1);
                
                const status = frm.doc.is_december_override ? 'Enabled' : 'Disabled';
                const indicator = frm.doc.is_december_override ? 'green' : 'blue';
                
                frappe.show_alert({
                    message: __('December Override {0}', [status]),
                    indicator: indicator
                }, 5);
                
                frm.refresh();
            }, __('Actions'));
        }
        
        // Add button to validate tax effects
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Validate Tax Effects'), function() {
                frappe.call({
                    method: 'payroll_indonesia.api.validate_payroll_tax_effects',
                    args: {
                        payroll_entry: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Validating Tax Effects...'),
                    callback: function(r) {
                        if (r.message) {
                            const result = r.message;
                            
                            if (result.status === 'success' && !result.missing_effects.length) {
                                frappe.msgprint({
                                    title: __('Tax Effects Validation'),
                                    indicator: 'green',
                                    message: __('All components have proper tax effect settings.')
                                });
                            } else {
                                let message = __('The following components are missing tax effect settings:') + '<ul>';
                                
                                if (result.missing_effects && result.missing_effects.length) {
                                    result.missing_effects.forEach(component => {
                                        message += `<li>${component.name} (${component.type})</li>`;
                                    });
                                }
                                
                                message += '</ul>';
                                
                                if (result.suggestion) {
                                    message += `<p>${result.suggestion}</p>`;
                                }
                                
                                frappe.msgprint({
                                    title: __('Missing Tax Effect Settings'),
                                    indicator: 'orange',
                                    message: message
                                });
                            }
                        }
                    }
                });
            }, __('Actions'));
        }
        
        // Add indicator for tax method
        if (frm.doc.calculate_indonesia_tax) {
            const tax_method = frm.doc.tax_method || 'Progressive';
            frm.dashboard.add_indicator(__(`Tax Method: ${tax_method}`), "blue");
        }
        
        // Add indicator for December Override
        if (frm.doc.is_december_override) {
            frm.dashboard.add_indicator(__("December Override Active"), "green");
        }
    },
    
    // Validasi tanggal - keep this to ensure payroll period is within the same month
    validate: function(frm) {
        if (frm.doc.start_date && frm.doc.end_date) {
            let start_month = moment(frm.doc.start_date).month();
            let end_month = moment(frm.doc.end_date).month();
            
            if (start_month !== end_month) {
                frappe.msgprint({
                    title: __("Peringatan"),
                    indicator: 'orange',
                    message: __("Untuk perhitungan pajak Indonesia, periode payroll sebaiknya berada dalam bulan yang sama.")
                });
            }
        }
        
        // Validate tax settings if Indonesia tax is enabled
        if (frm.doc.calculate_indonesia_tax) {
            // Ensure tax method is set
            if (!frm.doc.tax_method) {
                frm.set_value('tax_method', 'Progressive');
                frappe.show_alert({
                    message: __('Tax method set to Progressive (default)'),
                    indicator: 'blue'
                }, 5);
            }
        }
    },
    
    // Modified end_date handler to suggest December Override without strict validation
    end_date: function(frm) {
        if (frm.doc.end_date) {
            let end_month = moment(frm.doc.end_date).month(); // 0-indexed (December is 11)
            
            // Only show informational indicator if it's December, but don't enforce
            if (end_month === 11) { // December
                frm.dashboard.add_indicator(__("Bulan Desember - Pertimbangkan mengaktifkan December Override"), "blue");
                
                // If calculate_indonesia_tax is enabled, suggest enabling December Override but don't enforce
                if (frm.doc.calculate_indonesia_tax && !frm.doc.is_december_override) {
                    frappe.show_alert({
                        message: __('This appears to be a December payroll. Consider enabling December Override for annual tax correction.'),
                        indicator: 'blue'
                    }, 10);
                }
            }
        }
    },
    
    // When tax method changes, show appropriate message
    tax_method: function(frm) {
        if (frm.doc.tax_method === 'TER') {
            frappe.msgprint({
                title: __('TER Method Selected'),
                indicator: 'blue',
                message: __('TER method will use preset rates based on employee tax status. Make sure TER rates are properly configured in Payroll Indonesia Settings.')
            });
        }
    },
    
    // When calculate_indonesia_tax is toggled, update UI
    calculate_indonesia_tax: function(frm) {
        frm.refresh();
    }
});