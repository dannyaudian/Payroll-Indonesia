frappe.ui.form.on('Annual Payroll History', {
    refresh: function(frm) {
        calculate_totals(frm);
    }
});

frappe.ui.form.on('Annual Payroll History Child', {
    bruto: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    pengurang_netto: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    biaya_jabatan: function(frm, cdt, cdn) {
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
    annual_payroll_history_childs_add: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    annual_payroll_history_childs_remove: function(frm, cdt, cdn) {
        calculate_totals(frm);
    }
});

function calculate_totals(frm) {
    let bruto = 0, pengurang_netto = 0, biaya_jabatan = 0, netto = 0, pkp = 0, pph21 = 0;
    $.each(frm.doc.annual_payroll_history_childs || [], function(i, row) {
        bruto += flt(row.bruto);
        pengurang_netto += flt(row.pengurang_netto);
        biaya_jabatan += flt(row.biaya_jabatan);
        netto += flt(row.netto);
        pkp += flt(row.pkp);
        pph21 += flt(row.pph21);
    });
    frm.set_value('total_bruto', bruto);
    frm.set_value('total_pengurang_netto', pengurang_netto);
    frm.set_value('total_biaya_jabatan', biaya_jabatan);
    frm.set_value('total_netto', netto);
    frm.set_value('total_pkp', pkp);
    frm.set_value('total_pph21', pph21);
    frm.refresh_fields(['total_bruto', 'total_pengurang_netto', 'total_biaya_jabatan', 'total_netto', 'total_pkp', 'total_pph21']);
}