frappe.ui.form.on('Employee', {
    refresh: function(frm) {
        // Add custom buttons or functionality here
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
    }
});