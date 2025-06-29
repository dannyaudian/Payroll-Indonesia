// -*- coding: utf-8 -*-
// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-06-29 00:12:13 by dannyaudian

frappe.ui.form.on('BPJS Settings', {
    // Store cached validation limits
    __limits: {},
    
    refresh: function(frm) {
        frm.add_fetch('company', 'default_currency', 'currency');
        
        // Add action button for updating BPJS components
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Update BPJS Components"), function() {
                frappe.confirm(
                    __("Apakah Anda ingin memperbarui semua komponen BPJS pada salary slip yang belum disubmit?"),
                    function() {
                        // Yes - Update components
                        frappe.call({
                            method: "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.update_all_bpjs_components",
                            freeze: true,
                            freeze_message: __("Memperbarui komponen BPJS..."),
                            callback: function(r) {
                                frappe.msgprint(__("Komponen BPJS berhasil diperbarui."));
                            }
                        });
                    }
                );
            }, __("Aksi"));
        }
    },
    
    onload: function(frm) {
        // Fetch validation limits from server
        frappe.call({
            method: "payroll_indonesia.api.get_bpjs_limits",
            callback: function(r) {
                if (r.message) {
                    // Cache the limits for later use
                    frm.events.__limits = r.message;
                    console.log("BPJS validation limits loaded:", frm.events.__limits);
                }
            }
        });
    },
    
    setup: function(frm) {
        frm.set_query("company", function() {
            return {
                "filters": {
                    "country": "Indonesia"
                }
            };
        });
        
        // Set up validation for all percentage fields
        const percentage_fields = [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "jht_employee_percent",
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jkk_percent",
            "jkm_percent"
        ];
        
        percentage_fields.forEach(field => {
            frm.events[field] = function(frm) {
                validate_percentage(frm, field);
            };
        });
    }
});

/**
 * Validate percentage values against dynamically loaded limits
 * 
 * @param {Object} frm - Form object
 * @param {String} field - Field name to validate
 */
function validate_percentage(frm, field) {
    // Get the validation limits for this field
    const limits = frm.events.__limits;
    let min_value = 0;
    let max_value = 100;
    
    // Find specific field limit or use default
    if (limits && limits.percentage_ranges) {
        const field_limit = limits.percentage_ranges.find(rule => rule.field === field);
        if (field_limit) {
            min_value = field_limit.min || 0;
            max_value = field_limit.max || 100;
        }
    }
    
    // Default fallback values if server didn't provide limits
    if (!limits || Object.keys(limits).length === 0) {
        const default_limits = {
            "kesehatan_employee_percent": 5,
            "kesehatan_employer_percent": 10,
            "jht_employee_percent": 5,
            "jht_employer_percent": 10,
            "jp_employee_percent": 5,
            "jp_employer_percent": 5,
            "jkk_percent": 5,
            "jkm_percent": 5
        };
        max_value = default_limits[field] || 100;
    }
    
    // Validate and adjust value if needed
    if (frm.doc[field] < min_value) {
        frappe.model.set_value(frm.doctype, frm.docname, field, min_value);
        frappe.show_alert({
            message: __("Nilai minimum untuk {0} adalah {1}%", [
                frappe.meta.get_label(frm.doctype, field, frm.docname),
                min_value
            ]),
            indicator: 'red'
        });
    } else if (frm.doc[field] > max_value) {
        frappe.model.set_value(frm.doctype, frm.docname, field, max_value);
        frappe.show_alert({
            message: __("Nilai maksimum untuk {0} adalah {1}%", [
                frappe.meta.get_label(frm.doctype, field, frm.docname),
                max_value
            ]),
            indicator: 'red'
        });
    }
}
