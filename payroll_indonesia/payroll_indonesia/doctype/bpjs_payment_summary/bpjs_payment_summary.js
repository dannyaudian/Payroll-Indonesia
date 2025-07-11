// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-06-16 09:33:38 by dannyaudian

/**
 * BPJS Payment Summary Client Script
 * 
 * This script handles client-side functionality for the BPJS Payment Summary doctype,
 * including data fetching from salary slips, calculation of totals, and UI enhancements.
 */

// Helper utility functions
const flt = (value) => frappe.utils.flt(value);
const format_currency = (value, currency) => frappe.format_currency(value, currency);

// Month names in Indonesian
const MONTH_NAMES = [
    'Januari', 'Februari', 'Maret', 'April', 
    'Mei', 'Juni', 'Juli', 'Agustus', 
    'September', 'Oktober', 'November', 'Desember'
];

/**
 * Creates a debounced function that delays execution
 * and prevents multiple rapid calls
 * 
 * @param {Function} func - Function to debounce
 * @param {number} delay - Delay in milliseconds
 * @returns {Function} Debounced function
 */
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

/**
 * Fetch data from salary slips based on filter
 * 
 * @param {Object} frm - The form object
 * @returns {Promise<void>}
 */
async function fetchFromSalarySlip(frm) {
    // Validate required fields
    if (!frm.doc.company) {
        frappe.msgprint(__('Please select Company before fetching data'));
        return;
    }
    
    if (!frm.doc.month || !frm.doc.year) {
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
        
        if (result.message) {
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
 * 
 * @param {Object} frm - The form object
 * @returns {Promise<void>}
 */
async function refreshData(frm) {
    // Check if there are employee details with salary slip links
    if (!frm.doc.employee_details || !frm.doc.employee_details.some(d => d.salary_slip)) {
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
        
        if (result.message) {
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
 * 
 * @param {Object} frm - The form object
 */
function updateMonthName(frm) {
    if (!frm.doc.month || !frm.doc.year) return;
    
    if (frm.doc.month >= 1 && frm.doc.month <= 12) {
        const monthIndex = frm.doc.month - 1;
        
        // Set month_name if field exists
        if (frm.meta.fields.find(field => field.fieldname === "month_name")) {
            frm.set_value('month_name', MONTH_NAMES[monthIndex]);
        }
        
        // Set month_year_title if field exists
        if (frm.meta.fields.find(field => field.fieldname === "month_year_title")) {
            frm.set_value('month_year_title', `${MONTH_NAMES[monthIndex]} ${frm.doc.year}`);
        }
    }
}

/**
 * Calculate total from all BPJS components
 * 
 * @param {Object} frm - The form object
 */
function calculate_total(frm) {
    let total = 0;
    
    // Calculate from components table
    if (frm.doc.komponen) {
        frm.doc.komponen.forEach(d => {
            total += flt(d.amount);
        });
    }
    
    frm.set_value('total', total);
    frm.refresh_field('total');
    
    // Check if account details total matches components total
    calculate_account_details_total(frm);
}

/**
 * Calculate total from account details and compare with components total
 * 
 * @param {Object} frm - The form object
 */
function calculate_account_details_total(frm) {
    let account_total = 0;
    
    if (frm.doc.account_details) {
        frm.doc.account_details.forEach(d => {
            account_total += flt(d.amount);
        });
    }
    
    if (frm.doc.total && account_total > 0 && Math.abs(frm.doc.total - account_total) > 0.1) {
        // Set field if exists
        if (frm.meta.fields.find(field => field.fieldname === "account_total")) {
            frm.set_value('account_total', account_total);
            frm.refresh_field('account_total');
        }
        
        frappe.show_alert({
            message: __('Warning: Account details total ({0}) does not match components total ({1})', 
                [format_currency(account_total, frm.doc.currency), 
                 format_currency(frm.doc.total, frm.doc.currency)]),
            indicator: 'orange'
        });
    }
}

/**
 * Calculate totals from employee details
 * 
 * @param {Object} frm - The form object
 * @returns {Object} Totals for each BPJS type
 */
function calculate_employee_totals(frm) {
    if (!frm.doc.employee_details) {
        return {
            jht_total: 0,
            jp_total: 0,
            kesehatan_total: 0,
            jkk_total: 0,
            jkm_total: 0
        };
    }
    
    const totals = {
        jht_total: 0,
        jp_total: 0,
        kesehatan_total: 0,
        jkk_total: 0,
        jkm_total: 0
    };
    
    frm.doc.employee_details.forEach(d => {
        totals.jht_total += flt(d.jht_employee) + flt(d.jht_employer);
        totals.jp_total += flt(d.jp_employee) + flt(d.jp_employer);
        totals.kesehatan_total += flt(d.kesehatan_employee) + flt(d.kesehatan_employer);
        totals.jkk_total += flt(d.jkk);
        totals.jkm_total += flt(d.jkm);
    });
    
    return totals;
}

/**
 * Update components table based on employee details
 * 
 * @param {Object} frm - The form object
 */
function update_components_from_employees(frm) {
    if (!frm.doc.employee_details || frm.doc.employee_details.length === 0) return;
    
    try {
        // Get totals from employee details
        const totals = calculate_employee_totals(frm);
        
        // Clear existing components
        frm.clear_table('komponen');
        
        // Component definitions
        const components = [
            {
                name: 'JHT', 
                total: totals.jht_total,
                description: 'JHT Contribution (Employee + Employer)'
            },
            {
                name: 'JP', 
                total: totals.jp_total,
                description: 'JP Contribution (Employee + Employer)'
            },
            {
                name: 'JKK', 
                total: totals.jkk_total,
                description: 'JKK Contribution (Employer)'
            },
            {
                name: 'JKM', 
                total: totals.jkm_total,
                description: 'JKM Contribution (Employer)'
            },
            {
                name: 'Kesehatan', 
                total: totals.kesehatan_total,
                description: 'Kesehatan Contribution (Employee + Employer)'
            }
        ];
        
        // Add components if total > 0
        components.forEach(component => {
            if (component.total > 0) {
                const row = frm.add_child('komponen');
                row.component = `BPJS ${component.name}`;
                row.component_type = component.name;
                row.description = component.description;
                row.amount = component.total;
            }
        });
        
        frm.refresh_field('komponen');
        calculate_total(frm);
    } catch (error) {
        console.error("Error in update_components_from_employees:", error);
        frappe.msgprint({
            title: __('Error'),
            indicator: 'red',
            message: __('Error updating components: {0}', [error.message])
        });
    }
}

/**
 * Create Payment Entry for BPJS Payment
 * 
 * @param {Object} frm - The form object
 * @returns {Promise<void>}
 */
async function createPaymentEntry(frm) {
    try {
        await frappe.confirm(
            __('Are you sure you want to create Payment Entry for BPJS payment?')
        );
        
        frappe.show_progress(__('Processing'), 0, 100);
        const result = await frm.call({
            doc: frm.doc,
            method: 'generate_payment_entry',
            freeze: true,
            freeze_message: __('Creating Payment Entry...')
        });
        
        frappe.hide_progress();
        
        if (result.message) {
            frappe.show_alert({
                message: __('Payment Entry {0} created successfully. Please review and submit it.', [result.message]),
                indicator: 'green'
            });
            frm.refresh();
            frappe.set_route('Form', 'Payment Entry', result.message);
        }
    } catch (error) {
        frappe.hide_progress();
        frappe.throw(__('Error creating payment entry: {0}', [error.message]));
    }
}

// Main form event handlers
frappe.ui.form.on('BPJS Payment Summary', {
    refresh: function(frm) {
        // Add buttons after submission but before payment
        if (frm.doc.docstatus === 1) {
            // Add Generate Payment Entry button
            if (!frm.doc.payment_entry) {
                frm.add_custom_button(__('Create Payment Entry'), 
                    () => createPaymentEntry(frm), 
                    __('Create'));
            }
            
            // Add view buttons for payment entry and journal entry if they exist
            if (frm.doc.payment_entry) {
                frm.add_custom_button(__('View Payment Entry'), () => {
                    frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
                }, __('View'));
            }
            
            if (frm.doc.journal_entry) {
                frm.add_custom_button(__('View Journal Entry'), () => {
                    frappe.set_route('Form', 'Journal Entry', frm.doc.journal_entry);
                }, __('View'));
            }
        }
        
        // Add buttons for draft state
        if (frm.doc.docstatus === 0) {
            // Button to get data from Salary Slip - debounced 10s
            frm.add_custom_button(__('Ambil Data dari Salary Slip'), 
                debounce(async () => await fetchFromSalarySlip(frm), 10000), 
                __('Data')
            );
            
            // Button to refresh data
            frm.add_custom_button(__('Refresh Data'), 
                debounce(async () => await refreshData(frm), 10000),
                __('Data')
            );
            
            // Button to populate employee details
            if (frm.meta.fields.find(field => field.fieldname === "employee_details")) {
                if (!frm.doc.employee_details || frm.doc.employee_details.length === 0) {
                    frm.add_custom_button(__('Generate Employee Details'), 
                        debounce(async () => {
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
                            } catch (error) {
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
                debounce(async () => {
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
                    } catch (error) {
                        if (error) {
                            console.error("Error setting account details:", error);
                        }
                    }
                }, 10000),
                __('Actions')
            );
            
            // Button to sync with defaults.json - debounced 10s
            frm.add_custom_button(__('Sync with Defaults.json'), 
                debounce(async () => {
                    try {
                        await frappe.confirm(
                            __('This will update account details based on defaults.json configuration. Continue?')
                        );
                        
                        const result = await frappe.call({
                            method: "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_account_detail.bpjs_payment_account_detail.sync_with_defaults_json",
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
                    } catch (error) {
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
                
                // Update month name and title
                updateMonthName(frm);
            }
        }
        
        // Set default for salary_slip_filter if empty
        if (frm.doc.docstatus === 0 && 
            frm.meta.fields.find(field => field.fieldname === "salary_slip_filter") && 
            !frm.doc.salary_slip_filter) {
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
        
        if (filter_description) {
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
                frappe.model.set_value(
                    cdt, 
                    cdn, 
                    'reference_number', 
                    `BPJS-${row.account_type}-${frm.doc.month}-${frm.doc.year}`
                );
            }
        }
    }
});

// Employee detail calculations if applicable
frappe.ui.form.on('BPJS Payment Summary Detail', {
    employee_details_add: function(frm) {
        try {
            calculate_employee_totals(frm);
            update_components_from_employees(frm);
        } catch (error) {
            console.error("Error in employee_details_add:", error);
        }
    },
    
    // Handle changes to employee BPJS contribution fields
    jht_employee: function(frm) {
        update_components_from_employees(frm);
    },
    
    jp_employee: function(frm) {
        update_components_from_employees(frm);
    },
    
    kesehatan_employee: function(frm) {
        update_components_from_employees(frm);
    },
    
    jht_employer: function(frm) {
        update_components_from_employees(frm);
    },
    
    jp_employer: function(frm) {
        update_components_from_employees(frm);
    },
    
    jkk: function(frm) {
        update_components_from_employees(frm);
    },
    
    jkm: function(frm) {
        update_components_from_employees(frm);
    },
    
    kesehatan_employer: function(frm) {
        update_components_from_employees(frm);
    },
    
    employee_details_remove: function(frm) {
        calculate_employee_totals(frm);
        update_components_from_employees(frm);
    },
    
    // Handler for salary slip link
    salary_slip: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.salary_slip) {
            try {
                // Get BPJS data from this salary slip
                const result = await frappe.call({
                    method: "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.get_salary_slip_bpjs_data",
                    args: {
                        salary_slip: row.salary_slip
                    }
                });
                
                if (result.message) {
                    const data = result.message;
                    
                    // Update the current row with data from salary slip
                    const fieldsToUpdate = {
                        'jht_employee': data.jht_employee || 0,
                        'jp_employee': data.jp_employee || 0,
                        'kesehatan_employee': data.kesehatan_employee || 0,
                        'jht_employer': data.jht_employer || 0,
                        'jp_employer': data.jp_employer || 0,
                        'kesehatan_employer': data.kesehatan_employer || 0,
                        'jkk': data.jkk || 0,
                        'jkm': data.jkm || 0,
                        'last_updated': frappe.datetime.now_datetime(),
                        'is_synced': 1
                    };
                    
                    // Set all fields at once
                    Object.entries(fieldsToUpdate).forEach(([field, value]) => {
                        frappe.model.set_value(cdt, cdn, field, value);
                    });
                    
                    // Calculate the amount field
                    const amount = flt(data.jht_employee) + 
                                   flt(data.jp_employee) + 
                                   flt(data.kesehatan_employee) +
                                   flt(data.jht_employer) + 
                                   flt(data.jp_employer) + 
                                   flt(data.kesehatan_employer) +
                                   flt(data.jkk) + 
                                   flt(data.jkm);
                                  
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