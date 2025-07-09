// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-06-16 09:33:38 by dannyaudian

// Import required functions and ensure they're available
const flt = function(value) {
    return frappe.utils.flt(value);
};

const format_currency = function(value, currency) {
    return frappe.format_currency(value, currency);
};

// Create debounce function with configurable delay
function debounce(func, delay) {
    let timeoutId;
    return function(...args) {
        if (timeoutId) {
            frappe.show_alert({
                message: __('Please wait before trying again'),
                indicator: 'orange'
            });
            return;
        }
        
        func.apply(this, args);
        
        timeoutId = setTimeout(() => {
            timeoutId = null;
        }, delay);
    };
}

frappe.ui.form.on('BPJS Payment Summary', {
    refresh: function(frm) {
        // Add buttons after submission but before payment
        if(frm.doc.docstatus === 1) {
            // Add Generate Payment Entry button
            if(!frm.doc.payment_entry) {
                frm.add_custom_button(__('Create Payment Entry'), async function() {
                    await frappe.confirm(
                        __('Are you sure you want to create Payment Entry for BPJS payment?')
                    );
                    
                    try {
                        frappe.show_progress(__('Processing'), 0, 100);
                        const result = await frm.call({
                            doc: frm.doc,
                            method: 'generate_payment_entry',
                            freeze: true,
                            freeze_message: __('Creating Payment Entry...')
                        });
                        
                        frappe.hide_progress();
                        
                        if(result.message) {
                            frappe.show_alert({
                                message: __('Payment Entry {0} created successfully. Please review and submit it.', [result.message]),
                                indicator: 'green'
                            });
                            frm.refresh();
                            frappe.set_route('Form', 'Payment Entry', result.message);
                        }
                    } catch(error) {
                        frappe.hide_progress();
                        frappe.throw(__('Error creating payment entry: {0}', [error.message]));
                    }
                }, __('Create'));
            }
            
            // Add view buttons for payment entry and journal entry if they exist
            if(frm.doc.payment_entry) {
                frm.add_custom_button(__('View Payment Entry'), function() {
                    frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
                }, __('View'));
            }
            
            if(frm.doc.journal_entry) {
                frm.add_custom_button(__('View Journal Entry'), function() {
                    frappe.set_route('Form', 'Journal Entry', frm.doc.journal_entry);
                }, __('View'));
            }
        }
        
        // Add buttons for draft state
        if(frm.doc.docstatus === 0) {
            // Button to get data from Salary Slip - debounced 10s
            frm.add_custom_button(__('Ambil Data dari Salary Slip'), 
                debounce(async function() {
                    await fetchFromSalarySlip(frm);
                }, 10000), 
                __('Data')
            );
            
            // Button to refresh data
            frm.add_custom_button(__('Refresh Data'), 
                debounce(async function() {
                    await refreshData(frm);
                }, 10000),
                __('Data')
            );
            
            // Button to populate employee details
            if(frm.meta.fields.find(field => field.fieldname === "employee_details")) {
                if(!frm.doc.employee_details || frm.doc.employee_details.length === 0) {
                    frm.add_custom_button(__('Generate Employee Details'), 
                        debounce(async function() {
                            try {
                                await frappe.confirm(
                                    __('This will add all active employees with BPJS participation. Continue?')
                                );
                                
                                await frm.call({
                                    doc: frm.doc,
                                    method: 'populate_employee_details',
                                    freeze: true,
                                    freeze_message: __('Fetching employee details...')
                                });
                                
                                frm.refresh();
                            } catch(error) {
                                if (error) {
                                    console.error("Error generating employee details:", error);
                                }
                            }
                        }, 10000),
                        __('Actions')
                    );
                }
            }
            
            // Button to set account details - debounced 10s
            frm.add_custom_button(__('Set Account Details'), 
                debounce(async function() {
                    try {
                        await frappe.confirm(
                            __('This will update account details based on BPJS Settings. Continue?')
                        );
                        
                        await frm.call({
                            doc: frm.doc,
                            method: 'set_account_details',
                            freeze: true,
                            freeze_message: __('Setting account details...')
                        });
                        
                        frm.refresh();
                        frappe.show_alert({
                            message: __('Account details updated'),
                            indicator: 'green'
                        });
                    } catch(error) {
                        if (error) {
                            console.error("Error setting account details:", error);
                        }
                    }
                }, 10000),
                __('Actions')
            );
            
            // Button to sync with defaults.json - debounced 10s
            frm.add_custom_button(__('Sync with Defaults.json'), 
                debounce(async function() {
                    try {
                        await frappe.confirm(
                            __('This will update account details based on defaults.json configuration. Continue?')
                        );
                        
                        const result = await frappe.call({
                            method: "payroll_indonesia.doctype.bpjs_payment_account_detail.bpjs_payment_account_detail.sync_with_defaults_json",
                            args: {
                                doc: frm.doc
                            },
                            freeze: true,
                            freeze_message: __('Syncing account details...')
                        });
                        
                        if (result.message && result.message.accounts_added) {
                            frappe.show_alert({
                                message: __('Added {0} accounts from defaults.json', [result.message.accounts_added]),
                                indicator: 'green'
                            });
                            frm.refresh();
                        } else {
                            frappe.show_alert({
                                message: __('No accounts added. Check if defaults.json is properly configured.'),
                                indicator: 'orange'
                            });
                        }
                    } catch(error) {
                        if (error) {
                            console.error("Error syncing with defaults.json:", error);
                        }
                    }
                }, 10000),
                __('Actions')
            );
        }
    },
    
    onload: function(frm) {
        if (frm.is_new()) {
            // Set default values for new document
            frm.set_value('posting_date', frappe.datetime.get_today());
            frm.set_value('status', 'Draft');
            
            // Set month and year based on current date if not already set
            if (!frm.doc.month || !frm.doc.year) {
                const current_date = frappe.datetime.get_today().split('-');
                frm.set_value('year', parseInt(current_date[0]));
                frm.set_value('month', parseInt(current_date[1]));
                
                // Set month_name if field exists
                if (frm.meta.fields.find(field => field.fieldname === "month_name")) {
                    const month_names = [
                        'Januari', 'Februari', 'Maret', 'April', 
                        'Mei', 'Juni', 'Juli', 'Agustus', 
                        'September', 'Oktober', 'November', 'Desember'
                    ];
                    const month_index = parseInt(current_date[1]) - 1;
                    frm.set_value('month_name', month_names[month_index]);
                }
                
                // Set month_year_title if field exists
                if (frm.meta.fields.find(field => field.fieldname === "month_year_title")) {
                    const month_names = [
                        'Januari', 'Februari', 'Maret', 'April', 
                        'Mei', 'Juni', 'Juli', 'Agustus', 
                        'September', 'Oktober', 'November', 'Desember'
                    ];
                    const month_index = parseInt(current_date[1]) - 1;
                    frm.set_value('month_year_title', `${month_names[month_index]} ${current_date[0]}`);
                }
            }
        }
        
        // Set default for salary_slip_filter if empty
        if (frm.doc.docstatus === 0 && frm.meta.fields.find(field => field.fieldname === "salary_slip_filter") && !frm.doc.salary_slip_filter) {
            frm.set_value('salary_slip_filter', 'Periode Saat Ini');
        }
    },
    
    // Handlers for the buttons
    fetch_data: function(frm) {
        fetchFromSalarySlip(frm);
    },
    
    refresh_data: function(frm) {
        refreshData(frm);
    },
    
    salary_slip_filter: function(frm) {
        // Update description based on filter selection
        const filter = frm.doc.salary_slip_filter;
        let filter_description = "";
        
        switch(filter) {
            case "Periode Saat Ini":
                filter_description = `Hanya mengambil data salary slip dengan periode ${frm.doc.month_year_title}`;
                break;
            case "Periode Kustom":
                filter_description = "Anda dapat menentukan rentang tanggal kustom untuk mengambil data";
                break;
            case "Semua Slip Belum Terbayar":
                filter_description = "Mengambil semua salary slip yang belum tercakup dalam pembayaran BPJS";
                break;
        }
        
        if(filter_description) {
            frm.set_df_property('salary_slip_filter', 'description', filter_description);
            frm.refresh_field('salary_slip_filter');
        }
    },
    
    month: function(frm) {
        updateMonthName(frm);
    },
    
    year: function(frm) {
        updateMonthName(frm);
    },
    
    validate: function(frm) {
        // Basic validations
        if (!frm.doc.month || !frm.doc.year) {
            frappe.msgprint({
                title: __('Missing Required Fields'),
                indicator: 'red',
                message: __('Month and Year are mandatory fields.')
            });
            frappe.validated = false;
            return;
        }
        
        if (frm.doc.month < 1 || frm.doc.month > 12) {
            frappe.msgprint({
                title: __('Invalid Month'),
                indicator: 'red',
                message: __('Month must be between 1 and 12.')
            });
            frappe.validated = false;
            return;
        }
        
        // Calculate and validate totals
        calculate_total(frm);
        
        // Check if components exist
        if (!frm.doc.komponen || frm.doc.komponen.length === 0) {
            frappe.msgprint({
                title: __('Missing Components'),
                indicator: 'red',
                message: __('At least one BPJS component is required.')
            });
            frappe.validated = false;
            return;
        }
        
        // Check if account details exist
        if (!frm.doc.account_details || frm.doc.account_details.length === 0) {
            frappe.msgprint({
                title: __('Missing Account Details'),
                indicator: 'orange',
                message: __('Account details are not set. Click "Set Account Details" to generate them.')
            });
        }
    }
});

// Component child table calculations
frappe.ui.form.on('BPJS Payment Component', {
    komponen_add: function(frm) {
        calculate_total(frm);
    },
    
    component: function(frm, cdt, cdn) {
        // Set description automatically based on component
        const row = locals[cdt][cdn];
        if (row.component) {
            const descriptions = {
                "BPJS Kesehatan": "BPJS Kesehatan Monthly Payment",
                "BPJS JHT": "BPJS JHT Monthly Payment",
                "BPJS JP": "BPJS JP Monthly Payment",
                "BPJS JKK": "BPJS JKK Monthly Payment",
                "BPJS JKM": "BPJS JKM Monthly Payment"
            };
            
            if (descriptions[row.component] && !row.description) {
                frappe.model.set_value(cdt, cdn, 'description', descriptions[row.component]);
            }
            
            // Set component_type if empty
            if (!row.component_type) {
                const component_type = row.component.replace("BPJS ", "");
                frappe.model.set_value(cdt, cdn, 'component_type', component_type);
            }
        }
    },
    
    amount: function(frm) {
        calculate_total(frm);
    },
    
    komponen_remove: function(frm) {
        calculate_total(frm);
    }
});

// Account details child table calculations
frappe.ui.form.on('BPJS Payment Account Detail', {
    account_details_add: function(frm) {
        calculate_account_details_total(frm);
    },
    
    amount: function(frm) {
        calculate_account_details_total(frm);
    },
    
    account_details_remove: function(frm) {
        calculate_account_details_total(frm);
    },
    
    account_type: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        // Generate reference number based on account type and parent doc
        if (row.account_type) {
            if (!row.description) {
                frappe.model.set_value(cdt, cdn, 'description', `BPJS ${row.account_type} Payment`);
            }
            
            if (!row.reference_number && frm.doc.month && frm.doc.year) {
                frappe.model.set_value(cdt, cdn, 'reference_number', `BPJS-${row.account_type}-${frm.doc.month}-${frm.doc.year}`);
            }
        }
    }
});

// Employee detail calculations if applicable
frappe.ui.form.on('BPJS Payment Summary Detail', {
    employee_details_add: function(frm) {
        try {
            const totals = calculate_employee_totals(frm);
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in employee_details_add:", e);
        }
    },
    
    // Handle changes to all employee BPJS contribution fields
    jht_employee: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in jht_employee handler:", e);
        }
    },
    
    jp_employee: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in jp_employee handler:", e);
        }
    },
    
    kesehatan_employee: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in kesehatan_employee handler:", e);
        }
    },
    
    jht_employer: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in jht_employer handler:", e);
        }
    },
    
    jp_employer: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in jp_employer handler:", e);
        }
    },
    
    jkk: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in jkk handler:", e);
        }
    },
    
    jkm: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in jkm handler:", e);
        }
    },
    
    kesehatan_employer: function(frm) {
        try {
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in kesehatan_employer handler:", e);
        }
    },
    
    employee_details_remove: function(frm) {
        try {
            const totals = calculate_employee_totals(frm);
            update_components_from_employees(frm);
        } catch (e) {
            console.error("Error in employee_details_remove:", e);
        }
    },
    
    // New handler for salary slip link
    salary_slip: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.salary_slip) {
            try {
                // Get BPJS data from this salary slip
                const result = await frappe.call({
                    method: "payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.get_salary_slip_bpjs_data",
                    args: {
                        salary_slip: row.salary_slip
                    }
                });
                
                if (result.message) {
                    const data = result.message;
                    
                    // Update the current row with data from salary slip
                    frappe.model.set_value(cdt, cdn, 'jht_employee', data.jht_employee || 0);
                    frappe.model.set_value(cdt, cdn, 'jp_employee', data.jp_employee || 0);
                    frappe.model.set_value(cdt, cdn, 'kesehatan_employee', data.kesehatan_employee || 0);
                    frappe.model.set_value(cdt, cdn, 'jht_employer', data.jht_employer || 0);
                    frappe.model.set_value(cdt, cdn, 'jp_employer', data.jp_employer || 0);
                    frappe.model.set_value(cdt, cdn, 'kesehatan_employer', data.kesehatan_employer || 0);
                    frappe.model.set_value(cdt, cdn, 'jkk', data.jkk || 0);
                    frappe.model.set_value(cdt, cdn, 'jkm', data.jkm || 0);
                    frappe.model.set_value(cdt, cdn, 'last_updated', frappe.datetime.now_datetime());
                    frappe.model.set_value(cdt, cdn, 'is_synced', 1);
                    
                    // Calculate the amount field
                    const amount = frappe.utils.flt(data.jht_employee) + 
                                  frappe.utils.flt(data.jp_employee) + 
                                  frappe.utils.flt(data.kesehatan_employee) +
                                  frappe.utils.flt(data.jht_employer) + 
                                  frappe.utils.flt(data.jp_employer) + 
                                  frappe.utils.flt(data.kesehatan_employer) +
                                  frappe.utils.flt(data.jkk) + 
                                  frappe.utils.flt(data.jkm);
                                  
                    frappe.model.set_value(cdt, cdn, 'amount', amount);
                    
                    frappe.show_alert({
                        message: __('Data from salary slip loaded successfully'),
                        indicator: 'green'
                    });
                }
            } catch (error) {
                frappe.show_alert({
                    message: __('Error loading data from salary slip: {0}', [error.message]),
                    indicator: 'red'
                });
                console.error("Error loading salary slip data:", error);
            }
        }
    }
});

/**
 * Fetch data from salary slips based on filter
 * @param {Object} frm - The form object
 */
async function fetchFromSalarySlip(frm) {
    // Validate required fields
    if(!frm.doc.company) {
        frappe.msgprint(__('Please select Company before fetching data'));
        return;
    }
    
    if(!frm.doc.month || !frm.doc.year) {
        frappe.msgprint(__('Please set Month and Year before fetching data'));
        return;
    }
    
    try {
        // Confirm action with user
        await frappe.confirm(
            __('This will fetch BPJS data from Salary Slips and may overwrite existing data. Continue?')
        );
        
        // On confirm
        frappe.show_progress(__('Processing'), 0, 100);
        
        const result = await frm.call({
            doc: frm.doc,
            method: "get_from_salary_slip",
            freeze: true,
            freeze_message: __('Fetching data from salary slips...')
        });
        
        frappe.hide_progress();
        
        if(result.message) {
            frappe.show_alert({
                message: __('Successfully fetched data from {0} salary slips', [result.message.count]),
                indicator: 'green'
            });
            
            frm.reload_doc();
        }
    } catch (error) {
        frappe.hide_progress();
        if (error) {
            console.error("Error fetching from salary slip:", error);
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('Error fetching data: {0}', [error.message || error])
            });
        }
    }
}

/**
 * Refresh data from linked salary slips
 * @param {Object} frm - The form object
 */
async function refreshData(frm) {
    // Check if there are employee details with salary slip links
    if(!frm.doc.employee_details || !frm.doc.employee_details.some(d => d.salary_slip)) {
        frappe.msgprint(__('No linked salary slips found. Use "Ambil Data dari Salary Slip" first.'));
        return;
    }
    
    try {
        // Confirm action with user
        await frappe.confirm(
            __('This will refresh data from linked Salary Slips. Continue?')
        );
        
        frappe.show_progress(__('Processing'), 0, 100);
        
        const result = await frm.call({
            doc: frm.doc,
            method: "update_from_salary_slip",
            freeze: true,
            freeze_message: __('Refreshing data from salary slips...')
        });
        
        frappe.hide_progress();
        
        if(result.message) {
            frappe.show_alert({
                message: __('Successfully updated {0} records', [result.message.updated]),
                indicator: 'green'
            });
            
            // Set last_synced timestamp
            frm.set_value('last_synced', frappe.datetime.now_datetime());
            frm.refresh_field('last_synced');
            
            frm.reload_doc();
        }
    } catch (error) {
        frappe.hide_progress();
        if (error) {
            console.error("Error refreshing data:", error);
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('Error refreshing data: {0}', [error.message || error])
            });
        }
    }
}

/**
 * Update month name and month_year_title fields if they exist
 * @param {Object} frm - The form object
 */
function updateMonthName(frm) {
    if (!frm.doc.month || !frm.doc.year) return;
    
    const month_names = [
        'Januari', 'Februari', 'Maret', 'April', 
        'Mei', 'Juni', 'Juli', 'Agustus', 
        'September', 'Oktober', 'November', 'Desember'
    ];
    
    if (frm.doc.month >= 1 && frm.doc.month <= 12) {
        // Set month_name if field exists
        if (frm.meta.fields.find(field => field.fieldname === "month_name")) {
            frm.set_value('month_name', month_names[frm.doc.month - 1]);
        }
        
        // Set month_year_title if field exists
        if (frm.meta.fields.find(field => field.fieldname === "month_year_title")) {
            frm.set_value('month_year_title', `${month_names[frm.doc.month - 1]} ${frm.doc.year}`);
        }
    }
}

/**
 * Calculate total from all BPJS components
 * @param {Object} frm - The form object
 */
function calculate_total(frm) {
    let total = 0;
    
    // Calculate from components table
    if(frm.doc.komponen) {
        frm.doc.komponen.forEach(function(d) {
            total += frappe.utils.flt(d.amount);
        });
    }
    
    frm.set_value('total', total);
    frm.refresh_field('total');
    
    // Check if account details total matches components total
    calculate_account_details_total(frm);
}

/**
 * Calculate total from account details and compare with components total
 * @param {Object} frm - The form object
 */
function calculate_account_details_total(frm) {
    let account_total = 0;
    
    if(frm.doc.account_details) {
        frm.doc.account_details.forEach(function(d) {
            account_total += frappe.utils.flt(d.amount);
        });
    }
    
    if(frm.doc.total && account_total > 0 && Math.abs(frm.doc.total - account_total) > 0.1) {
        // Set field if exists
        if (frm.meta.fields.find(field => field.fieldname === "account_total")) {
            frm.set_value('account_total', account_total);
            frm.refresh_field('account_total');
        }
        
        frappe.show_alert({
            message: __('Warning: Account details total ({0}) does not match components total ({1})', 
                [frappe.format_currency(account_total, frm.doc.currency), 
                 frappe.format_currency(frm.doc.total, frm.doc.currency)]),
            indicator: 'orange'
        });
    }
}

/**
 * Calculate totals from employee details
 * @param {Object} frm - The form object
 * @returns {Object} Totals for each BPJS type
 */
function calculate_employee_totals(frm) {
    if(!frm.doc.employee_details) {
        return {
            jht_total: 0,
            jp_total: 0,
            kesehatan_total: 0,
            jkk_total: 0,
            jkm_total: 0
        };
    }
    
    let jht_total = 0;
    let jp_total = 0;
    let kesehatan_total = 0;
    let jkk_total = 0;
    let jkm_total = 0;
    
    frm.doc.employee_details.forEach(function(d) {
        jht_total += frappe.utils.flt(d.jht_employee) + frappe.utils.flt(d.jht_employer);
        jp_total += frappe.utils.flt(d.jp_employee) + frappe.utils.flt(d.jp_employer);
        kesehatan_total += frappe.utils.flt(d.kesehatan_employee) + frappe.utils.flt(d.kesehatan_employer);
        jkk_total += frappe.utils.flt(d.jkk);
        jkm_total += frappe.utils.flt(d.jkm);
    });
    
    return {
        jht_total: jht_total,
        jp_total: jp_total,
        kesehatan_total: kesehatan_total,
        jkk_total: jkk_total,
        jkm_total: jkm_total
    };
}

/**
 * Update components table based on employee details
 * @param {Object} frm - The form object
 */
function update_components_from_employees(frm) {
    if(!frm.doc.employee_details || frm.doc.employee_details.length === 0) return;
    
    try {
        // Get totals from employee details
        const totals = calculate_employee_totals(frm);
        
        // Clear existing components
        frm.clear_table('komponen');
        
        // Add JHT component
        if(totals.jht_total > 0) {
            const row = frm.add_child('komponen');
            row.component = 'BPJS JHT';
            row.component_type = 'JHT';
            row.description = 'JHT Contribution (Employee + Employer)';
            row.amount = totals.jht_total;
        }
        
        // Add JP component
        if(totals.jp_total > 0) {
            const row = frm.add_child('komponen');
            row.component = 'BPJS JP';
            row.component_type = 'JP';
            row.description = 'JP Contribution (Employee + Employer)';
            row.amount = totals.jp_total;
        }
        
        // Add JKK component
        if(totals.jkk_total > 0) {
            const row = frm.add_child('komponen');
            row.component = 'BPJS JKK';
            row.component_type = 'JKK';
            row.description = 'JKK Contribution (Employer)';
            row.amount = totals.jkk_total;
        }
        
        // Add JKM component
        if(totals.jkm_total > 0) {
            const row = frm.add_child('komponen');
            row.component = 'BPJS JKM';
            row.component_type = 'JKM';
            row.description = 'JKM Contribution (Employer)';
            row.amount = totals.jkm_total;
        }
        
        // Add Kesehatan component
        if(totals.kesehatan_total > 0) {
            const row = frm.add_child('komponen');
            row.component = 'BPJS Kesehatan';
            row.component_type = 'Kesehatan';
            row.description = 'Kesehatan Contribution (Employee + Employer)';
            row.amount = totals.kesehatan_total;
        }
        
        frm.refresh_field('komponen');
        calculate_total(frm);
    } catch (e) {
        console.error("Error in update_components_from_employees:", e);
        frappe.msgprint({
            title: __('Error'),
            indicator: 'red',
            message: __('Error updating components: {0}', [e.message])
        });
    }
}
