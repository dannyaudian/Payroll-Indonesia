// Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
// For license information, please see license.txt
// Last modified: 2025-04-26 05:19:23 by dannyaudian

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
        
        // Tambahkan field untuk penggunaan metode TER jika belum ada
        frappe.model.with_doctype('Payroll Entry', function() {
            let fields = frappe.get_meta('Payroll Entry').fields;
            let has_ter_field = fields.some(field => field.fieldname === 'use_ter_method');
            
            if (!has_ter_field && !frm.custom_buttons["Tambah Field TER"]) {
                frm.add_custom_button(__("Tambah Field TER"), function() {
                    frappe.call({
                        method: "frappe.client.insert",
                        args: {
                            doc: {
                                "doctype": "Custom Field",
                                "dt": "Payroll Entry",
                                "label": "Use TER Method",
                                "fieldname": "use_ter_method",
                                "fieldtype": "Check",
                                "insert_after": "deduct_tax_for_unsubmitted_tax_exemption_proof",
                                "description": "Use Tarif Efektif Rata-rata (TER) method for PPh 21 calculation"
                            }
                        },
                        callback: function(r) {
                            frappe.msgprint(__("Field untuk metode perhitungan TER telah ditambahkan. Mohon refresh halaman."));
                            frappe.set_route('Form', 'Payroll Entry', frm.doc.name);
                        }
                    });
                });
            }
        });
    },
    
    // Validasi tanggal
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
    },
    
    // Add method to check December special handling
    end_date: function(frm) {
        if (frm.doc.end_date) {
            let end_month = moment(frm.doc.end_date).month(); // 0-indexed (December is 11)
            
            if (end_month === 11) { // December
                frm.dashboard.add_indicator(__("Bulan Desember - Akan dilakukan perhitungan koreksi pajak tahunan"), "blue");
            }
        }
    }
});
