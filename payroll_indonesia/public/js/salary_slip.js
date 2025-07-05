frappe.ui.form.on('Salary Slip', {
    refresh: function(frm) {
        // Add custom buttons or functionality for Indonesian payroll
        if (frm.doc.is_final_gabung_suami) {
            frm.dashboard.add_indicator(__("NPWP Gabung Suami"), "blue");
        }
        
        // Add indicator for TER method
        if (frm.doc.is_using_ter) {
            frm.dashboard.add_indicator(__("Using TER Method") + ` (${frm.doc.ter_rate}%)`, "green");
        }
        
        // Add indicator for December correction
        if (frm.doc.koreksi_pph21 && frm.doc.is_december_override) {
            const indicator_color = frm.doc.koreksi_pph21 > 0 ? "orange" : "green";
            const indicator_text = frm.doc.koreksi_pph21 > 0 ? "Kurang Bayar" : "Lebih Bayar";
            frm.dashboard.add_indicator(__(`PPh 21 Koreksi: ${indicator_text}`), indicator_color);
        }
        
        // TAMBAHKAN INI: Tombol untuk Debug TER Calculation
        frm.add_custom_button(__('Debug TER Calc'), function() {
            let total_earnings = 0;
            (frm.doc.earnings || []).forEach(function(e) {
                total_earnings += flt(e.amount);
            });
            
            let pph21_amount = 0;
            (frm.doc.deductions || []).forEach(function(d) {
                if (d.salary_component === "PPh 21") {
                    pph21_amount += flt(d.amount);
                }
            });
            
            let using_ter = frm.doc.is_using_ter || 0;
            let ter_rate = (frm.doc.ter_rate || 0) / 100;
            let expected_ter_tax = total_earnings * ter_rate;
            
            let message = `
                <div style="max-width: 600px;">
                    <h3>TER Calculation Debug</h3>
                    <table class="table table-bordered">
                        <tr>
                            <td><strong>Gross Pay</strong></td>
                            <td>${format_currency(frm.doc.gross_pay)}</td>
                        </tr>
                        <tr>
                            <td><strong>Total Earnings</strong></td>
                            <td>${format_currency(total_earnings)}</td>
                        </tr>
                        <tr>
                            <td><strong>Menggunakan TER</strong></td>
                            <td>${using_ter ? 'Ya' : 'Tidak'}</td>
                        </tr>
                        <tr>
                            <td><strong>TER Rate</strong></td>
                            <td>${frm.doc.ter_rate || 0}%</td>
                        </tr>
                        <tr>
                            <td><strong>PPh 21 (Saved)</strong></td>
                            <td>${format_currency(pph21_amount)}</td>
                        </tr>
                        <tr>
                            <td><strong>Expected TER Tax</strong></td>
                            <td>${format_currency(expected_ter_tax)}</td>
                            <td>${Math.abs(pph21_amount - expected_ter_tax) > 1 ? 
                                  '<span style="color: red;">Mismatch!</span>' : 
                                  '<span style="color: green;">Match</span>'}</td>
                        </tr>
                    </table>
                    
                    ${Math.abs(frm.doc.gross_pay - total_earnings) > 1 ? 
                      `<div class="alert alert-warning">
                       gross_pay (${format_currency(frm.doc.gross_pay)}) berbeda dengan 
                       total earnings (${format_currency(total_earnings)}). 
                       Ini bisa menjadi indikasi masalah perhitungan.
                      </div>` : ''}
                </div>
            `;
            
            frappe.msgprint({
                title: __('TER Calculation Debug'),
                indicator: 'blue',
                message: message
            });
        }, __('Actions'));
        
        // TAMBAHKAN INI: Tombol untuk Fix TER Calculation
        if (frm.is_new() || frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Fix TER Calculation'), function() {
                if (!frm.doc.is_using_ter) {
                    frappe.msgprint("Slip gaji ini tidak menggunakan metode TER.");
                    return;
                }
                
                let total_earnings = 0;
                (frm.doc.earnings || []).forEach(function(e) {
                    total_earnings += flt(e.amount);
                });
                
                let ter_rate = (frm.doc.ter_rate || 0) / 100;
                let correct_tax = total_earnings * ter_rate;
                
                // Update PPh 21 component
                let found_pph21 = false;
                frm.doc.deductions.forEach(function(d) {
                    if (d.salary_component === "PPh 21") {
                        d.amount = correct_tax;
                        found_pph21 = true;
                    }
                });
                
                if (!found_pph21) {
                    frappe.msgprint("Komponen PPh 21 tidak ditemukan.");
                    return;
                }
                
                frm.refresh_field('deductions');
                frappe.msgprint({
                    title: __('TER Calculation Fixed'),
                    indicator: 'green',
                    message: __('PPh 21 sekarang dihitung langsung dari penghasilan bulanan: {0}', 
                                [format_currency(correct_tax)])
                });
            }).addClass('btn-primary');
        }
        
        // Add December Override toggle
        if (frm.is_new() || frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Toggle December Mode'), function() {
                // Toggle the is_december_override field
                frm.set_value('is_december_override', frm.doc.is_december_override ? 0 : 1);
                
                // Show an alert to indicate the change
                const status = frm.doc.is_december_override ? 'Enabled' : 'Disabled';
                const indicator = frm.doc.is_december_override ? 'green' : 'blue';
                
                frappe.show_alert({
                    message: __('December Override {0}', [status]),
                    indicator: indicator
                }, 5);
                
                // If enabling December mode, warn about TER
                if (frm.doc.is_december_override && frm.doc.is_using_ter) {
                    frappe.msgprint({
                        title: __('Warning: TER and December Override'),
                        indicator: 'orange',
                        message: __('December mode will use Progressive method as required by PMK 168/2023, even though TER is currently enabled.')
                    });
                }
            }, __('Actions'));
        }
        
        // Show December Override Indicator
        if (frm.doc.is_december_override) {
            frm.dashboard.add_indicator(__("December Override Active"), "blue");
        }
        
        // === TAX SUMMARY BUTTONS START ===
        // Only show tax summary options for submitted salary slips
        if (frm.doc.docstatus === 1) {
            // Add section header
            frm.add_custom_button(__('Tax Summary'), function() {}, "Actions").addClass('btn-default dropdown-toggle');
            
            // Button to view tax summary
            frm.add_custom_button(__('View Tax Summary'), function() {
                // Get employee and year from salary slip
                const employee = frm.doc.employee;
                const year = moment(frm.doc.end_date).year();
                
                // Call API to get tax summary status
                frappe.call({
                    method: 'payroll_indonesia.api.get_tax_summary_status',
                    args: {
                        employee: employee,
                        year: year
                    },
                    freeze: true,
                    freeze_message: __('Fetching Tax Summary Data...'),
                    callback: function(r) {
                        if (r.message && !r.message.error) {
                            // Display tax summary information
                            display_tax_summary_dialog(r.message, employee, year);
                        } else {
                            // Show error message
                            frappe.msgprint({
                                title: __('Tax Summary Error'),
                                indicator: 'red',
                                message: r.message.message || __('Error retrieving tax summary data')
                            });
                        }
                    }
                });
            }, __('Tax Summary'));
            
            // Button to refresh tax summary
            frm.add_custom_button(__('Refresh Tax Summary'), function() {
                frappe.confirm(
                    __('Are you sure you want to refresh tax summary for this salary slip? This will recalculate tax data using the current slip values.'),
                    function() {
                        // Yes - refresh tax summary
                        frappe.call({
                            method: 'payroll_indonesia.api.refresh_tax_summary',
                            args: {
                                salary_slip: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('Refreshing Tax Summary...'),
                            callback: function(r) {
                                if (r.message && r.message.status === 'success') {
                                    frappe.show_alert({
                                        message: __('Tax summary refreshed successfully'),
                                        indicator: 'green'
                                    }, 5);
                                    
                                    // Add option to view tax summary after refresh
                                    frappe.confirm(
                                        __('Tax summary has been refreshed. Do you want to view it now?'),
                                        function() {
                                            // Call view tax summary
                                            const employee = frm.doc.employee;
                                            const year = moment(frm.doc.end_date).year();
                                            
                                            frappe.call({
                                                method: 'payroll_indonesia.api.get_tax_summary_status',
                                                args: {
                                                    employee: employee,
                                                    year: year
                                                },
                                                callback: function(r) {
                                                    if (r.message && !r.message.error) {
                                                        display_tax_summary_dialog(r.message, employee, year);
                                                    }
                                                }
                                            });
                                        }
                                    );
                                } else {
                                    frappe.msgprint({
                                        title: __('Tax Summary Refresh Failed'),
                                        indicator: 'red',
                                        message: r.message ? r.message.message : __('Failed to refresh tax summary')
                                    });
                                }
                            }
                        });
                    }
                );
            }, __('Tax Summary'));
            
            // Button for force refreshing all tax summary for this employee
            frm.add_custom_button(__('Rebuild Annual Tax Data'), function() {
                const employee = frm.doc.employee;
                const year = moment(frm.doc.end_date).year();
                
                let d = new frappe.ui.Dialog({
                    title: __('Rebuild Annual Tax Data'),
                    fields: [
                        {
                            label: __('Employee'),
                            fieldname: 'employee',
                            fieldtype: 'Link',
                            options: 'Employee',
                            default: employee,
                            read_only: 1
                        },
                        {
                            label: __('Year'),
                            fieldname: 'year',
                            fieldtype: 'Int',
                            default: year,
                            read_only: 1
                        },
                        {
                            label: __('Force Rebuild'),
                            fieldname: 'force',
                            fieldtype: 'Check',
                            default: 0,
                            description: __('If checked, will delete and recreate tax summary')
                        },
                        {
                            label: __('Process as December'),
                            fieldname: 'is_december_override',
                            fieldtype: 'Check',
                            default: frm.doc.is_december_override || 0,
                            description: __('If checked, will apply December calculation logic')
                        }
                    ],
                    primary_action_label: __('Rebuild Tax Summary'),
                    primary_action: function() {
                        const values = d.get_values();
                        
                        frappe.call({
                            method: 'payroll_indonesia.api.refresh_tax_summary',
                            args: {
                                employee: values.employee,
                                year: values.year,
                                force: values.force,
                                is_december_override: values.is_december_override
                            },
                            freeze: true,
                            freeze_message: __('Rebuilding Annual Tax Data...'),
                            callback: function(r) {
                                if (r.message && r.message.status === 'success') {
                                    d.hide();
                                    frappe.show_alert({
                                        message: __('Annual tax data rebuild queued with {0} of {1} slips processed', 
                                            [r.message.processed, r.message.total_slips]),
                                        indicator: 'green'
                                    }, 10);
                                    
                                    // Add link to tax summary
                                    if (r.message.tax_summary) {
                                        frappe.set_route('Form', 'Employee Tax Summary', r.message.tax_summary);
                                    }
                                } else {
                                    frappe.msgprint({
                                        title: __('Tax Summary Rebuild Failed'),
                                        indicator: 'red',
                                        message: r.message ? r.message.message : __('Failed to rebuild tax summary')
                                    });
                                }
                            }
                        });
                    }
                });
                
                d.show();
            }, __('Tax Summary'));
        }
        // === TAX SUMMARY BUTTONS END ===
    },
    
    // Show payroll note in a dialog for better readability
    after_save: function(frm) {
        if (frm.doc.payroll_note && frm.doc.payroll_note.trim().length > 0) {
            // Create a button to view payroll calculation details
            frm.add_custom_button(__('View Tax Calculation'), function() {
                let d = new frappe.ui.Dialog({
                    title: __('PPh 21 Calculation Details'),
                    fields: [{
                        fieldtype: 'HTML',
                        fieldname: 'calculation_html'
                    }]
                });
                
                const noteContent = frm.doc.payroll_note
                    .replace(/\n/g, '<br>')
                    .replace(/===(.+?)===/g, '<strong>$1</strong>')
                    .replace(/Rp\s(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)/g, '<b>Rp $1</b>');
                
                d.fields_dict.calculation_html.$wrapper.html(
                    `<div style="max-height: 300px; overflow-y: auto; padding: 10px;">${noteContent}</div>`
                );
                
                d.show();
            }, __('Actions'));
        }
    },
    
    // When December Override is toggled, update the UI
    is_december_override: function(frm) {
        frm.refresh();
    }
});

// Function to display tax summary data in a dialog
function display_tax_summary_dialog(data, employee, year) {
    if (!data.tax_summary_exists) {
        frappe.msgprint({
            title: __('No Tax Summary Found'),
            indicator: 'orange',
            message: __('No tax summary exists for {0} in year {1}. Try refreshing the tax summary.', [employee, year])
        });
        return;
    }
    
    let d = new frappe.ui.Dialog({
        title: __('Employee Tax Summary - {0}', [year]),
        fields: [{
            fieldtype: 'HTML',
            fieldname: 'tax_summary_html'
        }],
        primary_action_label: __('View Full Tax Summary'),
        primary_action: function() {
            d.hide();
            frappe.set_route('Form', 'Employee Tax Summary', data.tax_summary.name);
        }
    });
    
    // Generate monthly tax data table
    let monthly_table = `
        <table class="table table-bordered table-striped table-hover">
            <thead>
                <tr>
                    <th>${__('Month')}</th>
                    <th>${__('Gross Pay')}</th>
                    <th>${__('Tax Amount')}</th>
                    <th>${__('TER Status')}</th>
                    <th>${__('December')}</th>
                    <th>${__('Status')}</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    for (let month_data of data.monthly_data || []) {
        // Skip if no slip or no data
        if (!month_data.has_slip && !month_data.has_data) continue;
        
        let status_indicator;
        if (month_data.has_data && month_data.has_slip) {
            status_indicator = '<span class="indicator green">Synchronized</span>';
        } else if (month_data.has_slip && !month_data.has_data) {
            status_indicator = '<span class="indicator red">Missing Tax Data</span>';
        } else if (!month_data.has_slip && month_data.has_data) {
            status_indicator = '<span class="indicator orange">Orphaned Data</span>';
        } else {
            status_indicator = '<span class="indicator gray">N/A</span>';
        }
        
        // Format TER status
        let ter_status = '';
        if (month_data.has_data && month_data.data) {
            ter_status = month_data.data.is_using_ter ? 
                `<span class="indicator blue">TER ${month_data.data.ter_rate}%</span>` : 
                '<span class="indicator gray">Progressive</span>';
        }
        
        // Format December status
        let december_status = '';
        if (month_data.has_data && month_data.data && month_data.data.is_december_override) {
            december_status = '<span class="indicator blue">Yes</span>';
        } else {
            december_status = '<span class="indicator gray">No</span>';
        }
        
        // Format gross pay and tax amount
        let gross_pay = month_data.has_data && month_data.data ? 
            month_data.data.formatted_gross : '-';
        let tax_amount = month_data.has_data && month_data.data ? 
            month_data.data.formatted_tax : '-';
        
        monthly_table += `
            <tr>
                <td>${month_data.month_name}</td>
                <td>${gross_pay}</td>
                <td>${tax_amount}</td>
                <td>${ter_status}</td>
                <td>${december_status}</td>
                <td>${status_indicator}</td>
            </tr>
        `;
    }
    
    monthly_table += `
            </tbody>
        </table>
    `;
    
    // Create summary info
    let summary_info = `
        <div class="row">
            <div class="col-sm-6">
                <div class="card" style="margin-bottom: 15px;">
                    <div class="card-body">
                        <h5 class="card-title">${__('Annual Tax Summary')}</h5>
                        <p><strong>${__('Year')}:</strong> ${year}</p>
                        <p><strong>${__('Employee')}:</strong> ${employee}</p>
                        <p><strong>${__('YTD Tax')}:</strong> ${data.tax_summary.formatted_ytd_tax}</p>
                        ${data.tax_summary.is_using_ter ? 
                            `<p><strong>${__('Using TER')}:</strong> ${data.tax_summary.ter_rate}%</p>` : ''}
                        ${data.tax_summary.is_december_override ? 
                            `<p><strong>${__('December Override')}:</strong> ${__('Yes')}</p>` : ''}
                    </div>
                </div>
            </div>
            <div class="col-sm-6">
                <div class="card" style="margin-bottom: 15px;">
                    <div class="card-body">
                        <h5 class="card-title">${__('Status')}</h5>
                        <p><strong>${__('Months with Data')}:</strong> ${data.stats.months_with_data} / 12</p>
                        <p><strong>${__('Months with Salary Slips')}:</strong> ${data.stats.potential_months}</p>
                        ${data.needs_refresh ? 
                            `<div class="alert alert-warning">
                                ${data.refresh_recommendation}
                            </div>` : 
                            `<div class="alert alert-success">
                                ${__('Tax summary is up to date with all salary slips.')}
                            </div>`
                        }
                    </div>
                </div>
            </div>
        </div>
    `;
    
    d.fields_dict.tax_summary_html.$wrapper.html(
        `<div style="max-height: 500px; overflow-y: auto; padding: 10px;">
            ${summary_info}
            <h4>${__('Monthly Tax Details')}</h4>
            ${monthly_table}
        </div>`
    );
    
    d.show();
}
