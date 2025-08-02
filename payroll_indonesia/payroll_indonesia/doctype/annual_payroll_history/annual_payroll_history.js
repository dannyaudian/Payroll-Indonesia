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
    monthly_details_add: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    monthly_details_remove: function(frm, cdt, cdn) {
        calculate_totals(frm);
    }
});

function calculate_totals(frm) {
    let bruto = 0, netto = 0, pkp = 0, pph21 = 0;
    $.each(frm.doc.monthly_details || [], function(i, row) {
        bruto += flt(row.bruto);
        netto += flt(row.netto);
        pkp += flt(row.pkp);
        pph21 += flt(row.pph21);
    });
    frm.set_value('bruto_total', bruto);
    frm.set_value('netto_total', netto);
    frm.set_value('pkp_annual', pkp);
    frm.set_value('pph21_annual', pph21);
    frm.refresh_fields(['bruto_total', 'netto_total', 'pkp_annual', 'pph21_annual']);
}