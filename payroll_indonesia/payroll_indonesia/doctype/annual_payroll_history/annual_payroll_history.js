frappe.ui.form.on('Annual Payroll History', {
    refresh: function(frm) {
        calculate_totals(frm);
    },
    before_cancel: function(frm) {
        return new Promise((resolve, reject) => {
            frappe.confirm(
                __(
                    'Urutan pembatalan:<br>' +
                    '1. Batalkan semua Salary Slip terkait.<br>' +
                    '2. Batalkan dokumen Annual Payroll History ini.<br><br>' +
                    'Lanjutkan pembatalan?'
                ),
                () => resolve(),
                () => reject()
            );
        });
    }
});

frappe.ui.form.on('Annual Payroll History Child', {
    bruto: function(frm, cdt, cdn) {
        auto_calculate_netto(frm, cdt, cdn);
        calculate_totals(frm);
    },
    pengurang_netto: function(frm, cdt, cdn) {
        auto_calculate_netto(frm, cdt, cdn);
        calculate_totals(frm);
    },
    biaya_jabatan: function(frm, cdt, cdn) {
        auto_calculate_netto(frm, cdt, cdn);
        calculate_totals(frm);
    },
    netto: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    pkp: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    pph21: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    monthly_details_add: function(frm, cdt, cdn) {
        // set "bulan" to the current length of monthly_details when a row is added
        if (frm.doc.monthly_details) {
            frappe.model.set_value(cdt, cdn, 'bulan', frm.doc.monthly_details.length);
        }
        calculate_totals(frm);
    },
    monthly_details_remove: function(frm, cdt, cdn) {
        calculate_totals(frm);
    }
});

/**
 * Automatically calculate netto value when bruto, pengurang_netto, or biaya_jabatan changes
 * Formula: netto = bruto - pengurang_netto - biaya_jabatan
 */
function auto_calculate_netto(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const bruto = flt(row.bruto || 0);
    const pengurang_netto = flt(row.pengurang_netto || 0);
    const biaya_jabatan = flt(row.biaya_jabatan || 0);
    
    // Calculate netto based on the formula
    const calculated_netto = bruto - pengurang_netto - biaya_jabatan;
    
    // Only update if there's a significant difference (avoids circular updates)
    if (Math.abs(calculated_netto - flt(row.netto || 0)) > 0.1) {
        frappe.model.set_value(cdt, cdn, 'netto', calculated_netto);
    }
}

/**
 * Calculate all totals for the parent document based on child rows
 */
function calculate_totals(frm) {
    let bruto_total = 0, 
        netto_total = 0, 
        pkp_annual = 0, 
        pph21_annual = 0,
        pengurang_netto_total = 0,
        biaya_jabatan_total = 0;
    
    // Iterate through all monthly details
    $.each(frm.doc.monthly_details || [], function(i, row) {
        bruto_total += flt(row.bruto || 0);
        netto_total += flt(row.netto || 0);
        pkp_annual += flt(row.pkp || 0);
        pph21_annual += flt(row.pph21 || 0);
        pengurang_netto_total += flt(row.pengurang_netto || 0);
        biaya_jabatan_total += flt(row.biaya_jabatan || 0);
    });
    
    // Calculate the expected netto total based on the formula
    const calculated_netto_total = bruto_total - pengurang_netto_total - biaya_jabatan_total;
    
    // Log a warning if there's a significant difference between calculated and stored netto
    if (Math.abs(calculated_netto_total - netto_total) > 1) {
        console.warn(`Netto total mismatch: calculated=${calculated_netto_total}, sum of rows=${netto_total}, diff=${calculated_netto_total - netto_total}`);
        
        // Optionally use calculated value instead of sum of rows
        // netto_total = calculated_netto_total;
    }
    
    // Update parent fields
    frm.set_value('bruto_total', bruto_total);
    frm.set_value('netto_total', netto_total);
    frm.set_value('pkp_annual', pkp_annual);
    frm.set_value('pph21_annual', pph21_annual);
    
    // Only set these fields if they exist in the doctype
    if (frm.fields_dict['pengurang_netto_total']) {
        frm.set_value('pengurang_netto_total', pengurang_netto_total);
    }
    if (frm.fields_dict['biaya_jabatan_total']) {
        frm.set_value('biaya_jabatan_total', biaya_jabatan_total);
    }
    
    // Refresh all total fields
    frm.refresh_fields([
        'bruto_total', 
        'netto_total', 
        'pkp_annual', 
        'pph21_annual',
        'pengurang_netto_total',
        'biaya_jabatan_total'
    ]);
}
