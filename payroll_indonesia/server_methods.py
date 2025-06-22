import frappe
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_december_pph


@frappe.whitelist()
def calculate_december_pph_for_payroll(payroll_entry_name):
    """
    Server method to recalculate December PPh for all salary slips in a payroll entry
    """
    try:
        # Get all salary slips for this payroll entry
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={"payroll_entry": payroll_entry_name, "docstatus": ["!=", 2]},
            fields=["name", "employee"],
        )

        results = []

        for slip_data in salary_slips:
            try:
                # Get salary slip document
                slip = frappe.get_doc("Salary Slip", slip_data.name)

                # Get employee document
                employee = frappe.get_doc("Employee", slip_data.employee)

                # Force December calculation
                slip.is_december_override = 1
                calculate_december_pph(slip, employee)

                # Save the updated slip
                slip.save()

                results.append(
                    {
                        "salary_slip": slip_data.name,
                        "employee": slip_data.employee,
                        "status": "success",
                    }
                )

            except Exception as e:
                results.append(
                    {
                        "salary_slip": slip_data.name,
                        "employee": slip_data.employee,
                        "status": "error",
                        "error": str(e),
                    }
                )

        return {
            "success": True,
            "message": f"Processed {len(salary_slips)} salary slips",
            "results": results,
        }

    except Exception as e:
        frappe.log_error(f"Error in December calculation: {str(e)}")
        return {"success": False, "message": str(e)}
