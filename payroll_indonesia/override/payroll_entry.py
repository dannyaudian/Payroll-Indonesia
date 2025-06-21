# # -*- coding: utf-8 -*-
# # Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# # For license information, please see license.txt

# from __future__ import unicode_literals
# import frappe
# from frappe.model.document import Document
# from dateutil.relativedelta import relativedelta
# from frappe.utils import cint, flt, nowdate, add_days, getdate, fmt_money, add_to_date, DATE_FORMAT
# from frappe import _
# from erpnext.accounts.utils import get_fiscal_year
# import calendar
# import datetime


# class PayrollEntry(Document):

#     def should_run_as_december(self) -> bool:
#         """
#         Expose checkbox value from field `is_december_run` (default False).
#         This determines if salary slips should use December progressive logic.
#         """
#         return bool(self.get("is_december_run", 0))

#     def validate(self):
#         """Add validation to ensure December logic is properly configured"""
#         super().validate() if hasattr(super(), "validate") else None

#         if self.should_run_as_december():
#             frappe.logger().info(f"Payroll Entry {self.name} marked for December processing")

#             # Optional warning if not December period
#             if self.end_date:
#                 end_month = getdate(self.end_date).month
#                 if end_month != 12:
#                     frappe.msgprint(
#                         _(
#                             "December Progressive Logic is enabled but payroll period doesn't end in December. "
#                             "Please verify this is intended."
#                         ),
#                         indicator="yellow",
#                     )

#     def on_submit(self):
#         self.create_salary_slips()

#     def get_emp_list(self):
#         """
#         Returns list of active employees based on selected criteria
#         and for which salary structure exists
#         """
#         cond = self.get_filter_condition()
#         cond += self.get_joining_releiving_condition()

#         condition = ""
#         if self.payroll_frequency:
#             condition = """and payroll_frequency = '%(payroll_frequency)s'""" % {
#                 "payroll_frequency": self.payroll_frequency
#             }

#         sal_struct = frappe.db.sql(
#             """
#                 select
#                     name from `tabSalary Structure`
#                 where
#                     docstatus != 2 and
#                     is_active = 'Yes'
#                     and company = %(company)s and
#                     ifnull(salary_slip_based_on_timesheet,0) = %(salary_slip_based_on_timesheet)s
#                     {condition}""".format(
#                 condition=condition
#             ),
#             {
#                 "company": self.company,
#                 "salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
#             },
#         )

#         if sal_struct:
#             cond += "and t2.parent IN %(sal_struct)s "
#             emp_list = frappe.db.sql(
#                 """
#                 select
#                     t1.name as employee, t1.employee_name, t1.department, t1.designation
#                 from
#                     `tabEmployee` t1, `tabSalary Structure Employee` t2
#                 where
#                     t1.docstatus!=2
#                     and t1.name = t2.employee
#             %s """
#                 % cond,
#                 {"sal_struct": sal_struct},
#                 as_dict=True,
#             )
#             return emp_list

#     def fill_employee_details(self):
#         self.set("employees", [])
#         employees = self.get_emp_list()
#         if not employees:
#             frappe.throw(_("No employees for the mentioned criteria"))

#         for d in employees:
#             self.append("employees", d)

#     def get_filter_condition(self):
#         self.check_mandatory()

#         cond = ""
#         for f in ["company", "branch", "department", "designation"]:
#             if self.get(f):
#                 cond += " and t1." + f + " = '" + self.get(f).replace("'", "'") + "'"

#         return cond

#     def get_joining_releiving_condition(self):
#         cond = """
#             and ifnull(t1.date_of_joining, '0000-00-00') <= '%(end_date)s'
#             and ifnull(t1.relieving_date, '2199-12-31') >= '%(start_date)s'
#         """ % {
#             "start_date": self.start_date,
#             "end_date": self.end_date,
#         }
#         return cond

#     def check_mandatory(self):
#         for fieldname in ["company", "start_date", "end_date"]:
#             if not self.get(fieldname):
#                 frappe.throw(_("Please set {0}").format(self.meta.get_label(fieldname)))

#     # def create_salary_slips(self):
#     #     """
#     #     Creates salary slip for selected employees if already not created
#     #     """
#     #     self.check_permission("write")
#     #     self.created = 1
#     #     emp_list = self.get_emp_list()
#     #     ss_list = []
#     #     if emp_list:
#     #         for emp in emp_list:
#     #             if not frappe.db.sql(
#     #                 """select
#     #                     name from `tabSalary Slip`
#     #                 where
#     #                     docstatus!= 2 and
#     #                     employee = %s and
#     #                     start_date >= %s and
#     #                     end_date <= %s and
#     #                     company = %s
#     #                     """,
#     #                 (emp["employee"], self.start_date, self.end_date, self.company),
#     #             ):
#     #                 ss = frappe.get_doc(
#     #                     {
#     #                         "doctype": "Salary Slip",
#     #                         "salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
#     #                         "payroll_frequency": self.payroll_frequency,
#     #                         "start_date": self.start_date,
#     #                         "end_date": self.end_date,
#     #                         "employee": emp["employee"],
#     #                         "employee_name": frappe.get_value(
#     #                             "Employee", {"name": emp["employee"]}, "employee_name"
#     #                         ),
#     #                         "company": self.company,
#     #                         "posting_date": self.posting_date,
#     #                         "is_december_override": self.should_run_as_december(),
#     #                     }
#     #                 )
#     #                 ss.insert()
#     #                 ss_dict = {}
#     #                 ss_dict["Employee Name"] = ss.employee_name
#     #                 ss_dict["Total Pay"] = fmt_money(
#     #                     ss.rounded_total, currency=frappe.defaults.get_global_default("currency")
#     #                 )
#     #                 ss_dict["Salary Slip"] = format_as_links(ss.name)[0]
#     #                 ss_list.append(ss_dict)
#     #     return create_log(ss_list)

#     def create_salary_slips(self):
#         """
#         Creates salary slip for selected employees if already not created
#         FIXED: Now properly passes December override flag
#         """
#         self.check_permission("write")
#         self.created = 1
#         emp_list = self.get_emp_list()
#         ss_list = []

#         # FIXED: Get December flag consistently
#         is_december_run = self.should_run_as_december()

#         # Log December processing
#         if is_december_run:
#             frappe.logger().info(
#                 f"Creating salary slips with December override for Payroll Entry {self.name}"
#             )

#         if emp_list:
#             for emp in emp_list:
#                 if not frappe.db.sql(
#                     """select
#                         name from `tabSalary Slip`
#                     where
#                         docstatus!= 2 and
#                         employee = %s and
#                         start_date >= %s and
#                         end_date <= %s and
#                         company = %s
#                         """,
#                     (emp["employee"], self.start_date, self.end_date, self.company),
#                 ):
#                     ss = frappe.get_doc(
#                         {
#                             "doctype": "Salary Slip",
#                             "salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
#                             "payroll_frequency": self.payroll_frequency,
#                             "start_date": self.start_date,
#                             "end_date": self.end_date,
#                             "employee": emp["employee"],
#                             "employee_name": frappe.get_value(
#                                 "Employee", {"name": emp["employee"]}, "employee_name"
#                             ),
#                             "company": self.company,
#                             "posting_date": self.posting_date,
#                             "payroll_entry": self.name,
#                             # FIXED: Add December override flag
#                             "is_december_override": cint(is_december_run),
#                         }
#                     )
#                     ss.insert()

#                     # Log individual salary slip creation with December flag
#                     if is_december_run:
#                         frappe.logger().info(
#                             f"Created salary slip {ss.name} for {emp['employee']} with December override = True"
#                         )

#                     ss_dict = {}
#                     ss_dict["Employee Name"] = ss.employee_name
#                     ss_dict["Total Pay"] = fmt_money(
#                         ss.rounded_total, currency=frappe.defaults.get_global_default("currency")
#                     )
#                     ss_dict["Salary Slip"] = format_as_links(ss.name)[0]
#                     ss_list.append(ss_dict)
#         return create_log(ss_list)

#     def get_sal_slip_list(self, ss_status, as_dict=False):
#         """Returns list of salary slips based on selected criteria"""
#         cond = self.get_filter_condition()

#         ss_list = frappe.db.sql(
#             """
#             select t1.name, t1.salary_structure from `tabSalary Slip` t1
#             where t1.docstatus = %s and t1.start_date >= %s and t1.end_date <= %s
#             and (t1.journal_entry is null or t1.journal_entry = "") and ifnull(salary_slip_based_on_timesheet,0) = %s %s
#         """
#             % ("%s", "%s", "%s", "%s", cond),
#             (ss_status, self.start_date, self.end_date, self.salary_slip_based_on_timesheet),
#             as_dict=as_dict,
#         )
#         return ss_list

#     def submit_salary_slips(self):
#         """Submit all salary slips based on selected criteria"""
#         self.check_permission("write")

#         jv_name = ""
#         ss_list = self.get_sal_slip_list(ss_status=0)
#         submitted_ss = []
#         not_submitted_ss = []
#         for ss in ss_list:
#             ss_obj = frappe.get_doc("Salary Slip", ss[0])
#             ss_dict = {}
#             ss_dict["Employee Name"] = ss_obj.employee_name
#             ss_dict["Total Pay"] = fmt_money(
#                 ss_obj.net_pay, currency=frappe.defaults.get_global_default("currency")
#             )
#             ss_dict["Salary Slip"] = format_as_links(ss_obj.name)[0]

#             if ss_obj.net_pay < 0:
#                 not_submitted_ss.append(ss_dict)
#             else:
#                 try:
#                     ss_obj.submit()
#                     submitted_ss.append(ss_dict)

#                 except frappe.ValidationError:
#                     not_submitted_ss.append(ss_dict)
#         if submitted_ss:
#             jv_name = self.make_accural_jv_entry()
#             frappe.msgprint(
#                 _("Salary Slip submitted for period from {0} to {1}").format(
#                     ss_obj.start_date, ss_obj.end_date
#                 )
#             )

#         return create_submit_log(submitted_ss, not_submitted_ss, jv_name)

#     def get_loan_details(self):
#         """
#         Get loan details from submitted salary slip based on selected criteria
#         """
#         cond = self.get_filter_condition()
#         return (
#             frappe.db.sql(
#                 """ select eld.employee_loan_account,
#                 eld.interest_income_account, eld.principal_amount, eld.interest_amount, eld.total_payment
#             from
#                 `tabSalary Slip` t1, `tabSalary Slip Loan` eld
#             where
#                 t1.docstatus = 1 and t1.name = eld.parent and start_date >= %s and end_date <= %s %s
#             """
#                 % ("%s", "%s", cond),
#                 (self.start_date, self.end_date),
#                 as_dict=True,
#             )
#             or []
#         )

#     def get_total_salary_amount(self):
#         """
#         Get total salary amount from submitted salary slip based on selected criteria
#         """
#         cond = self.get_filter_condition()
#         totals = frappe.db.sql(
#             """ select sum(rounded_total) as rounded_total from `tabSalary Slip` t1
#             where t1.docstatus = 1 and start_date >= %s and end_date <= %s %s
#             """
#             % ("%s", "%s", cond),
#             (self.start_date, self.end_date),
#             as_dict=True,
#         )
#         return totals and totals[0] or None

#     def get_salary_component_account(self, salary_component):
#         account = frappe.db.get_value(
#             "Salary Component Account",
#             {"parent": salary_component, "company": self.company},
#             "default_account",
#         )

#         if not account:
#             frappe.throw(
#                 _("Please set default account in Salary Component {0}").format(salary_component)
#             )

#         return account

#     def get_salary_components(self, component_type):
#         salary_slips = self.get_sal_slip_list(ss_status=1, as_dict=True)
#         if salary_slips:
#             salary_components = frappe.db.sql(
#                 """select salary_component, amount, parentfield
#                 from `tabSalary Detail` where parentfield = '%s' and parent in (%s)"""
#                 % (component_type, ", ".join(["%s"] * len(salary_slips))),
#                 tuple([d.name for d in salary_slips]),
#                 as_dict=True,
#             )
#             return salary_components

#     def get_salary_component_total(self, component_type=None):
#         salary_components = self.get_salary_components(component_type)
#         if salary_components:
#             component_dict = {}
#             for item in salary_components:
#                 component_dict[item["salary_component"]] = (
#                     component_dict.get(item["salary_component"], 0) + item["amount"]
#                 )
#             account_details = self.get_account(component_dict=component_dict)
#             return account_details

#     def get_account(self, component_dict=None):
#         account_dict = {}
#         for s, a in component_dict.items():
#             account = self.get_salary_component_account(s)
#             account_dict[account] = account_dict.get(account, 0) + a
#         return account_dict

#     def get_default_payroll_payable_account(self):
#         payroll_payable_account = frappe.db.get_value(
#             "Company", {"company_name": self.company}, "default_payroll_payable_account"
#         )

#         if not payroll_payable_account:
#             frappe.throw(
#                 _("Please set Default Payroll Payable Account in Company {0}").format(self.company)
#             )

#         return payroll_payable_account

#     def make_accural_jv_entry(self):
#         self.check_permission("write")
#         earnings = self.get_salary_component_total(component_type="earnings") or {}
#         deductions = self.get_salary_component_total(component_type="deductions") or {}
#         default_payroll_payable_account = self.get_default_payroll_payable_account()
#         loan_details = self.get_loan_details()
#         jv_name = ""
#         precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")

#         if earnings or deductions:
#             journal_entry = frappe.new_doc("Journal Entry")
#             journal_entry.voucher_type = "Journal Entry"
#             journal_entry.user_remark = _(
#                 "Accural Journal Entry for salaries from {0} to {1}"
#             ).format(self.start_date, self.end_date)
#             journal_entry.company = self.company
#             journal_entry.posting_date = nowdate()

#             accounts = []
#             payable_amount = 0

#             # Earnings
#             for acc, amount in earnings.items():
#                 payable_amount += flt(amount, precision)
#                 accounts.append(
#                     {
#                         "account": acc,
#                         "debit_in_account_currency": flt(amount, precision),
#                         "cost_center": self.cost_center,
#                         "project": self.project,
#                     }
#                 )

#             # Deductions
#             for acc, amount in deductions.items():
#                 payable_amount -= flt(amount, precision)
#                 accounts.append(
#                     {
#                         "account": acc,
#                         "credit_in_account_currency": flt(amount, precision),
#                         "cost_center": self.cost_center,
#                         "project": self.project,
#                     }
#                 )

#             # Employee loan
#             for data in loan_details:
#                 accounts.append(
#                     {
#                         "account": data.employee_loan_account,
#                         "credit_in_account_currency": data.principal_amount,
#                     }
#                 )
#                 accounts.append(
#                     {
#                         "account": data.interest_income_account,
#                         "credit_in_account_currency": data.interest_amount,
#                         "cost_center": self.cost_center,
#                         "project": self.project,
#                     }
#                 )
#                 payable_amount -= flt(data.total_payment, precision)

#             # Payable amount
#             accounts.append(
#                 {
#                     "account": default_payroll_payable_account,
#                     "credit_in_account_currency": flt(payable_amount, precision),
#                 }
#             )

#             journal_entry.set("accounts", accounts)
#             journal_entry.save()

#             try:
#                 journal_entry.submit()
#                 jv_name = journal_entry.name
#                 self.update_salary_slip_status(jv_name=jv_name)
#             except Exception as e:
#                 frappe.msgprint(e)

#         return jv_name

#     def make_payment_entry(self):
#         self.check_permission("write")
#         total_salary_amount = self.get_total_salary_amount()
#         default_payroll_payable_account = self.get_default_payroll_payable_account()
#         precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")

#         if total_salary_amount and total_salary_amount.rounded_total:
#             journal_entry = frappe.new_doc("Journal Entry")
#             journal_entry.voucher_type = "Bank Entry"
#             journal_entry.user_remark = _("Payment of salary from {0} to {1}").format(
#                 self.start_date, self.end_date
#             )
#             journal_entry.company = self.company
#             journal_entry.posting_date = nowdate()

#             payment_amount = flt(total_salary_amount.rounded_total, precision)

#             journal_entry.set(
#                 "accounts",
#                 [
#                     {"account": self.payment_account, "credit_in_account_currency": payment_amount},
#                     {
#                         "account": default_payroll_payable_account,
#                         "debit_in_account_currency": payment_amount,
#                         "reference_type": self.doctype,
#                         "reference_name": self.name,
#                     },
#                 ],
#             )
#             return journal_entry.as_dict()
#         else:
#             frappe.msgprint(
#                 _("There are no submitted Salary Slips to process."), title="Error", indicator="red"
#             )

#     def update_salary_slip_status(self, jv_name=None):
#         ss_list = self.get_sal_slip_list(ss_status=1)
#         for ss in ss_list:
#             ss_obj = frappe.get_doc("Salary Slip", ss[0])
#             frappe.db.set_value("Salary Slip", ss_obj.name, "status", "Paid")
#             frappe.db.set_value("Salary Slip", ss_obj.name, "journal_entry", jv_name)

#     def set_start_end_dates(self):
#         self.update(
#             get_start_end_dates(
#                 self.payroll_frequency, self.start_date or self.posting_date, self.company
#             )
#         )


# @frappe.whitelist()
# def get_start_end_dates(payroll_frequency, start_date=None, company=None):
#     """Returns dict of start and end dates for given payroll frequency based on start_date"""

#     if (
#         payroll_frequency == "Monthly"
#         or payroll_frequency == "Bimonthly"
#         or payroll_frequency == ""
#     ):
#         fiscal_year = get_fiscal_year(start_date, company=company)[0]
#         month = "%02d" % getdate(start_date).month
#         m = get_month_details(fiscal_year, month)
#         if payroll_frequency == "Bimonthly":
#             if getdate(start_date).day <= 15:
#                 start_date = m["month_start_date"]
#                 end_date = m["month_mid_end_date"]
#             else:
#                 start_date = m["month_mid_start_date"]
#                 end_date = m["month_end_date"]
#         else:
#             start_date = m["month_start_date"]
#             end_date = m["month_end_date"]

#     if payroll_frequency == "Weekly":
#         end_date = add_days(start_date, 6)

#     if payroll_frequency == "Fortnightly":
#         end_date = add_days(start_date, 13)

#     if payroll_frequency == "Daily":
#         end_date = start_date

#     return frappe._dict({"start_date": start_date, "end_date": end_date})


# def get_frequency_kwargs(frequency_name):
#     frequency_dict = {
#         "monthly": {"months": 1},
#         "fortnightly": {"days": 14},
#         "weekly": {"days": 7},
#         "daily": {"days": 1},
#     }
#     return frequency_dict.get(frequency_name)


# @frappe.whitelist()
# def get_end_date(start_date, frequency):
#     start_date = getdate(start_date)
#     frequency = frequency.lower() if frequency else "monthly"
#     kwargs = (
#         get_frequency_kwargs(frequency)
#         if frequency != "bimonthly"
#         else get_frequency_kwargs("monthly")
#     )

#     # weekly, fortnightly and daily intervals have fixed days so no problems
#     end_date = add_to_date(start_date, **kwargs) - relativedelta(days=1)
#     if frequency != "bimonthly":
#         return dict(end_date=end_date.strftime(DATE_FORMAT))

#     else:
#         return dict(end_date="")


# def get_month_details(year, month):
#     ysd = frappe.db.get_value("Fiscal Year", year, "year_start_date")
#     if ysd:
#         diff_mnt = cint(month) - cint(ysd.month)
#         if diff_mnt < 0:
#             diff_mnt = 12 - int(ysd.month) + cint(month)
#         msd = ysd + relativedelta(months=diff_mnt)  # month start date
#         month_days = cint(calendar.monthrange(cint(msd.year), cint(month))[1])  # days in month
#         mid_start = datetime.date(msd.year, cint(month), 16)  # month mid start date
#         mid_end = datetime.date(msd.year, cint(month), 15)  # month mid end date
#         med = datetime.date(msd.year, cint(month), month_days)  # month end date
#         return frappe._dict(
#             {
#                 "year": msd.year,
#                 "month_start_date": msd,
#                 "month_end_date": med,
#                 "month_mid_start_date": mid_start,
#                 "month_mid_end_date": mid_end,
#                 "month_days": month_days,
#             }
#         )
#     else:
#         frappe.throw(_("Fiscal Year {0} not found").format(year))


# @frappe.whitelist()
# def create_log(ss_list):
#     if not ss_list:
#         frappe.throw(
#             _(
#                 "There's no employee for the given criteria. Check that Salary Slips have not already been created."
#             ),
#             title="Error",
#         )
#     return ss_list


# def format_as_links(salary_slip):
#     return ['<a href="#Form/Salary Slip/{0}">{0}</a>'.format(salary_slip)]


# def create_submit_log(submitted_ss, not_submitted_ss, jv_name):
#     if not submitted_ss and not not_submitted_ss:
#         frappe.msgprint(
#             "No salary slip found to submit for the above selected criteria OR salary slip already submitted"
#         )

#     if not_submitted_ss:
#         frappe.msgprint(
#             "Could not submit any Salary Slip <br>\
#             Possible reasons: <br>\
#             1. Net pay is less than 0. <br>\
#             2. Company Email Address specified in employee master is not valid. <br>"
#         )


# def get_salary_slip_list(name, docstatus, as_dict=0):
#     payroll_entry = frappe.get_doc("Payroll Entry", name)

#     salary_slip_list = frappe.db.sql(
#         "select t1.name, t1.salary_structure from `tabSalary Slip` t1 "
#         "where t1.docstatus = %s "
#         "and t1.start_date >= %s "
#         "and t1.end_date <= %s",
#         (docstatus, payroll_entry.start_date, payroll_entry.end_date),
#         as_dict=as_dict,
#     )

#     return salary_slip_list


# @frappe.whitelist()
# def payroll_entry_has_created_slips(name):
#     response = {}

#     draft_salary_slips = get_salary_slip_list(name, docstatus=0)
#     submitted_salary_slips = get_salary_slip_list(name, docstatus=1)

#     response["draft"] = 1 if draft_salary_slips else 0
#     response["submitted"] = 1 if submitted_salary_slips else 0

#     return response


# def get_payroll_entry_bank_entries(payroll_entry_name):
#     journal_entries = frappe.db.sql(
#         "select name from `tabJournal Entry Account` "
#         'where reference_type="Payroll Entry" '
#         "and reference_name=%s and docstatus=1",
#         payroll_entry_name,
#         as_dict=1,
#     )

#     return journal_entries


# @frappe.whitelist()
# def payroll_entry_has_bank_entries(name):
#     response = {}

#     bank_entries = get_payroll_entry_bank_entries(name)
#     response["submitted"] = 1 if bank_entries else 0

#     return response

# -*- coding: utf-8 -*-
# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from dateutil.relativedelta import relativedelta
from frappe.utils import cint, nowdate, add_days, getdate, fmt_money, add_to_date, DATE_FORMAT
from frappe import _
from erpnext.accounts.utils import get_fiscal_year
import calendar
import datetime


class PayrollEntry(Document):

    def should_run_as_december(self) -> bool:
        """
        Expose checkbox value from field `is_december_run` (default False).
        This determines if salary slips should use December progressive logic.
        """
        return bool(self.get("is_december_run", 0))

    def is_december_period(self) -> bool:
        """
        Check if the payroll period is for December month
        """
        if self.end_date:
            return getdate(self.end_date).month == 12
        return False

    def calculate_december_tax_adjustment(self, employee_data):
        """
        Calculate December tax adjustment based on Indonesian tax rules
        Args:
            employee_data: dict containing employee salary details
        Returns:
            dict with December tax calculations
        """
        # Get annual salary components
        annual_gross = employee_data.get("annual_gross", 0)
        annual_bpjs = employee_data.get("annual_bpjs", 0)

        # Calculate Biaya Jabatan (5% dari gaji, maksimal 6 juta setahun)
        biaya_jabatan = min(annual_gross * 0.05, 6000000)

        # Calculate Iuran BPJS
        iuran_bpjs = annual_bpjs

        # Gaji Netto
        gaji_netto = annual_gross - biaya_jabatan - iuran_bpjs

        # PTKP (assuming TK1 - need to get from employee master)
        ptkp = employee_data.get("ptkp_amount", 58500000)  # Default TK1

        # PKP (Penghasilan Kena Pajak)
        pkp = max(0, gaji_netto - ptkp)

        # Calculate PPH21 Terutang using progressive tax rates
        pph21_terutang = self.calculate_progressive_tax(pkp)

        # PPH21 yang telah dibayar bulan sebelumnya
        pph21_paid_before = employee_data.get("pph21_paid_ytd", 0)

        # December adjustment
        december_adjustment = pph21_terutang - pph21_paid_before

        return {
            "annual_gross": annual_gross,
            "biaya_jabatan": biaya_jabatan,
            "iuran_bpjs": iuran_bpjs,
            "gaji_netto": gaji_netto,
            "ptkp": ptkp,
            "pkp": pkp,
            "pph21_terutang": pph21_terutang,
            "pph21_paid_before": pph21_paid_before,
            "december_adjustment": december_adjustment,
        }

    def calculate_progressive_tax(self, pkp):
        """
        Calculate Indonesian progressive tax (PPh21) based on PKP
        Tax brackets for 2024:
        - 5% for 0-60 million
        - 15% for 60-250 million
        - 25% for 250-500 million
        - 30% for 500 million-5 billion
        - 35% for >5 billion
        """
        if pkp <= 0:
            return 0

        tax_brackets = [
            (60000000, 0.05),  # 5% for first 60M
            (250000000, 0.15),  # 15% for 60M-250M
            (500000000, 0.25),  # 25% for 250M-500M
            (5000000000, 0.30),  # 30% for 500M-5B
            (float("inf"), 0.35),  # 35% for >5B
        ]

        total_tax = 0
        remaining_pkp = pkp
        previous_bracket = 0

        for bracket_limit, rate in tax_brackets:
            if remaining_pkp <= 0:
                break

            taxable_in_bracket = min(remaining_pkp, bracket_limit - previous_bracket)
            total_tax += taxable_in_bracket * rate
            remaining_pkp -= taxable_in_bracket
            previous_bracket = bracket_limit

        return total_tax

    def get_employee_annual_data(self, employee):
        """
        Get employee's annual salary data for December calculation
        """
        current_year = getdate(self.end_date).year

        # Try to get data from Employee Tax Summary first
        tax_summary = frappe.db.get_value(
            "Employee Tax Summary", {"employee": employee, "year": current_year}, ["name"]
        )

        if tax_summary:
            # Get monthly tax data from Employee Tax Summary
            monthly_data = frappe.db.sql(
                """
                SELECT
                    SUM(gross_pay) as annual_gross,
                    SUM(tax_amount) as pph21_paid_ytd
                FROM `tabMonthly Tax Detail`
                WHERE parent = %s
                AND month <= 11
            """,
                (tax_summary,),
                as_dict=True,
            )

            if monthly_data and monthly_data[0]:
                annual_gross = monthly_data[0].get("annual_gross", 0) or 0
                pph21_paid_ytd = monthly_data[0].get("pph21_paid_ytd", 0) or 0
            else:
                annual_gross = 0
                pph21_paid_ytd = 0
        else:
            # Fallback to Salary Slip data
            year_start = f"{current_year}-01-01"
            november_end = f"{current_year}-11-30"

            salary_data = frappe.db.sql(
                """
                SELECT
                    SUM(IFNULL(gross_pay, 0)) as annual_gross,
                    SUM(IFNULL(total_deduction, 0)) as total_deductions
                FROM `tabSalary Slip`
                WHERE employee = %s
                AND start_date >= %s
                AND end_date <= %s
                AND docstatus = 1
            """,
                (employee, year_start, november_end),
                as_dict=True,
            )

            # Get PPh21 from salary detail
            pph21_data = frappe.db.sql(
                """
                SELECT SUM(IFNULL(sd.amount, 0)) as pph21_paid_ytd
                FROM `tabSalary Detail` sd
                INNER JOIN `tabSalary Slip` ss ON sd.parent = ss.name
                WHERE ss.employee = %s
                AND ss.start_date >= %s
                AND ss.end_date <= %s
                AND ss.docstatus = 1
                AND sd.salary_component IN (
                    SELECT name FROM `tabSalary Component`
                    WHERE component_type = 'Deduction'
                    AND (salary_component_abbr = 'PPh21' OR name LIKE '%%PPh21%%')
                )
            """,
                (employee, year_start, november_end),
                as_dict=True,
            )

            if salary_data and salary_data[0]:
                annual_gross = salary_data[0].get("annual_gross", 0) or 0
            else:
                annual_gross = 0

            if pph21_data and pph21_data[0]:
                pph21_paid_ytd = pph21_data[0].get("pph21_paid_ytd", 0) or 0
            else:
                pph21_paid_ytd = 0

        # Get BPJS data (assuming it's a deduction component)
        year_start = f"{current_year}-01-01"
        november_end = f"{current_year}-11-30"

        bpjs_data = frappe.db.sql(
            """
            SELECT SUM(IFNULL(sd.amount, 0)) as annual_bpjs
            FROM `tabSalary Detail` sd
            INNER JOIN `tabSalary Slip` ss ON sd.parent = ss.name
            WHERE ss.employee = %s
            AND ss.start_date >= %s
            AND ss.end_date <= %s
            AND ss.docstatus = 1
            AND sd.salary_component IN (
                SELECT name FROM `tabSalary Component`
                WHERE component_type = 'Deduction'
                AND (name LIKE '%%BPJS%%' OR salary_component_abbr LIKE '%%BPJS%%')
            )
        """,
            (employee, year_start, november_end),
            as_dict=True,
        )

        annual_bpjs = 0
        if bpjs_data and bpjs_data[0]:
            annual_bpjs = bpjs_data[0].get("annual_bpjs", 0) or 0

        # Get employee PTKP
        employee_doc = frappe.get_doc("Employee", employee)
        ptkp_amount = self.get_ptkp_amount(employee_doc)

        annual_data = {
            "annual_gross": annual_gross,
            "annual_bpjs": annual_bpjs,
            "pph21_paid_ytd": pph21_paid_ytd,
            "ptkp_amount": ptkp_amount,
        }

        frappe.logger().info(f"Annual data for {employee}: {annual_data}")

        return annual_data

    def get_ptkp_amount(self, employee_doc):
        """
        Get PTKP amount based on employee marital status and dependents
        PTKP 2024 rates:
        - TK/0: 54,000,000
        - TK/1: 58,500,000
        - TK/2: 63,000,000
        - TK/3: 67,500,000
        - K/0: 58,500,000
        - K/1: 63,000,000
        - K/2: 67,500,000
        - K/3: 72,000,000
        """
        ptkp_rates = {
            "TK/0": 54000000,
            "TK/1": 58500000,
            "TK/2": 63000000,
            "TK/3": 67500000,
            "K/0": 58500000,
            "K/1": 63000000,
            "K/2": 67500000,
            "K/3": 72000000,
        }

        # Get PTKP status from employee (you may need to add this field)
        ptkp_status = employee_doc.get("ptkp_status", "TK/1")
        return ptkp_rates.get(ptkp_status, 58500000)  # Default TK/1

    def validate(self):
        """Add validation to ensure December logic is properly configured"""
        super().validate() if hasattr(super(), "validate") else None

        if self.should_run_as_december():
            frappe.logger().info(f"Payroll Entry {self.name} marked for December processing")

            # Optional warning if not December period
            if self.end_date and not self.is_december_period():
                frappe.msgprint(
                    _(
                        "December Progressive Logic is enabled but payroll period doesn't end in December. "
                        "Please verify this is intended."
                    ),
                    indicator="yellow",
                )

    def on_submit(self):
        self.create_salary_slips()

    def get_emp_list(self):
        """
        Returns list of active employees based on selected criteria
        and for which salary structure exists
        """
        cond = self.get_filter_condition()
        cond += self.get_joining_releiving_condition()

        condition = ""
        if self.payroll_frequency:
            condition = """and payroll_frequency = '%(payroll_frequency)s'""" % {
                "payroll_frequency": self.payroll_frequency
            }

        sal_struct = frappe.db.sql(
            """
                select
                    name from `tabSalary Structure`
                where
                    docstatus != 2 and
                    is_active = 'Yes'
                    and company = %(company)s and
                    ifnull(salary_slip_based_on_timesheet,0) = %(salary_slip_based_on_timesheet)s
                    {condition}""".format(
                condition=condition
            ),
            {
                "company": self.company,
                "salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
            },
        )

        if sal_struct:
            cond += "and t2.parent IN %(sal_struct)s "
            emp_list = frappe.db.sql(
                """
                select
                    t1.name as employee, t1.employee_name, t1.department, t1.designation
                from
                    `tabEmployee` t1, `tabSalary Structure Employee` t2
                where
                    t1.docstatus!=2
                    and t1.name = t2.employee
            %s """
                % cond,
                {"sal_struct": sal_struct},
                as_dict=True,
            )
            return emp_list

    def fill_employee_details(self):
        self.set("employees", [])
        employees = self.get_emp_list()
        if not employees:
            frappe.throw(_("No employees for the mentioned criteria"))

        for d in employees:
            self.append("employees", d)

    def get_filter_condition(self):
        self.check_mandatory()

        cond = ""
        for f in ["company", "branch", "department", "designation"]:
            if self.get(f):
                cond += " and t1." + f + " = '" + self.get(f).replace("'", "'") + "'"

        return cond

    def get_joining_releiving_condition(self):
        cond = """
            and ifnull(t1.date_of_joining, '0000-00-00') <= '%(end_date)s'
            and ifnull(t1.relieving_date, '2199-12-31') >= '%(start_date)s'
        """ % {
            "start_date": self.start_date,
            "end_date": self.end_date,
        }
        return cond

    def check_mandatory(self):
        for fieldname in ["company", "start_date", "end_date"]:
            if not self.get(fieldname):
                frappe.throw(_("Please set {0}").format(self.meta.get_label(fieldname)))

    def create_salary_slips(self):
        """
        Creates salary slip for selected employees if already not created
        Enhanced with December tax calculation logic
        """
        self.check_permission("write")
        self.created = 1
        emp_list = self.get_emp_list()
        ss_list = []

        # Get December flag consistently
        is_december_run = self.should_run_as_december()
        is_december_period = self.is_december_period()

        # Log December processing
        if is_december_run:
            frappe.logger().info(
                f"Creating salary slips with December override for Payroll Entry {self.name}"
            )

        if emp_list:
            for emp in emp_list:
                if not frappe.db.sql(
                    """select
                        name from `tabSalary Slip`
                    where
                        docstatus!= 2 and
                        employee = %s and
                        start_date >= %s and
                        end_date <= %s and
                        company = %s
                        """,
                    (emp["employee"], self.start_date, self.end_date, self.company),
                ):

                    # Prepare salary slip data
                    salary_slip_data = {
                        "doctype": "Salary Slip",
                        "salary_slip_based_on_timesheet": self.salary_slip_based_on_timesheet,
                        "payroll_frequency": self.payroll_frequency,
                        "start_date": self.start_date,
                        "end_date": self.end_date,
                        "employee": emp["employee"],
                        "employee_name": frappe.get_value(
                            "Employee", {"name": emp["employee"]}, "employee_name"
                        ),
                        "company": self.company,
                        "posting_date": self.posting_date,
                        "payroll_entry": self.name,
                        "is_december_override": cint(is_december_run),
                    }

                    # Add December tax calculation data if applicable
                    if is_december_run and is_december_period:
                        annual_data = self.get_employee_annual_data(emp["employee"])
                        december_calc = self.calculate_december_tax_adjustment(annual_data)

                        # Add December calculation fields to salary slip
                        salary_slip_data.update(
                            {
                                "december_annual_gross": december_calc["annual_gross"],
                                "december_biaya_jabatan": december_calc["biaya_jabatan"],
                                "december_iuran_bpjs": december_calc["iuran_bpjs"],
                                "december_gaji_netto": december_calc["gaji_netto"],
                                "december_ptkp": december_calc["ptkp"],
                                "december_pkp": december_calc["pkp"],
                                "december_pph21_terutang": december_calc["pph21_terutang"],
                                "december_pph21_paid_before": december_calc["pph21_paid_before"],
                                "december_tax_adjustment": december_calc["december_adjustment"],
                            }
                        )

                        frappe.logger().info(
                            f"December tax calculation for {emp['employee']}: "
                            f"PKP={december_calc['pkp']}, "
                            f"PPh21 Terutang={december_calc['pph21_terutang']}, "
                            f"Adjustment={december_calc['december_adjustment']}"
                        )

                    ss = frappe.get_doc(salary_slip_data)
                    ss.insert()

                    # Log individual salary slip creation with December flag
                    if is_december_run:
                        frappe.logger().info(
                            f"Created salary slip {ss.name} for {emp['employee']} with December override = True"
                        )

                    ss_dict = {}
                    ss_dict["Employee Name"] = ss.employee_name
                    ss_dict["Total Pay"] = fmt_money(
                        ss.rounded_total, currency=frappe.defaults.get_global_default("currency")
                    )
                    ss_dict["Salary Slip"] = format_as_links(ss.name)[0]
                    ss_list.append(ss_dict)
        return create_log(ss_list)

    def get_sal_slip_list(self, ss_status, as_dict=False):
        """Returns list of salary slips based on selected criteria"""
        cond = self.get_filter_condition()

        ss_list = frappe.db.sql(
            """
            select t1.name, t1.salary_structure from `tabSalary Slip` t1
            where t1.docstatus = %s and t1.start_date >= %s and t1.end_date <= %s
            and (t1.journal_entry is null or t1.journal_entry = "") and ifnull(salary_slip_based_on_timesheet,0) = %s %s
        """
            % ("%s", "%s", "%s", "%s", cond),
            (ss_status, self.start_date, self.end_date, self.salary_slip_based_on_timesheet),
            as_dict=as_dict,
        )
        return ss_list

    def submit_salary_slips(self):
        """Submit all salary slips based on selected criteria"""
        self.check_permission("write")

        jv_name = ""
        ss_list = self.get_sal_slip_list(ss_status=0)
        submitted_ss = []
        not_submitted_ss = []
        for ss in ss_list:
            ss_obj = frappe.get_doc("Salary Slip", ss[0])
            ss_dict = {}
            ss_dict["Employee Name"] = ss_obj.employee_name
            ss_dict["Total Pay"] = fmt_money(
                ss_obj.net_pay, currency=frappe.defaults.get_global_default("currency")
            )
            ss_dict["Salary Slip"] = format_as_links(ss_obj.name)[0]

            if ss_obj.net_pay < 0:
                not_submitted_ss.append(ss_dict)
            else:
                try:
                    ss_obj.submit()
                    submitted_ss.append(ss_dict)

                except frappe.ValidationError:
                    not_submitted_ss.append(ss_dict)
        if submitted_ss:
            jv_name = self.make_accural_jv_entry()
            frappe.msgprint(
                _("Salary Slip submitted for period from {0} to {1}").format(
                    ss_obj.start_date, ss_obj.end_date
                )
            )

        return create_submit_log(submitted_ss, not_submitted_ss, jv_name)


# Utility functions for December tax calculation
@frappe.whitelist()
def calculate_employee_december_tax(employee, year=None):
    """
    Standalone function to calculate December tax for specific employee
    """
    if not year:
        year = nowdate()[:4]

    # Create temporary payroll entry for calculation
    temp_payroll = frappe.new_doc("Payroll Entry")
    temp_payroll.end_date = f"{year}-12-31"

    annual_data = temp_payroll.get_employee_annual_data(employee)
    december_calc = temp_payroll.calculate_december_tax_adjustment(annual_data)

    return december_calc


@frappe.whitelist()
def preview_december_tax_calculations(payroll_entry_name):
    """
    Preview December tax calculations for all employees in payroll entry
    """
    payroll_entry = frappe.get_doc("Payroll Entry", payroll_entry_name)

    if not payroll_entry.should_run_as_december():
        return {"error": "This payroll entry is not marked for December processing"}

    emp_list = payroll_entry.get_emp_list()
    calculations = []

    for emp in emp_list:
        annual_data = payroll_entry.get_employee_annual_data(emp["employee"])
        december_calc = payroll_entry.calculate_december_tax_adjustment(annual_data)

        calculations.append(
            {
                "employee": emp["employee"],
                "employee_name": emp["employee_name"],
                "calculations": december_calc,
            }
        )

    return calculations


# Original utility functions remain the same
@frappe.whitelist()
def get_start_end_dates(payroll_frequency, start_date=None, company=None):
    """Returns dict of start and end dates for given payroll frequency based on start_date"""

    if (
        payroll_frequency == "Monthly"
        or payroll_frequency == "Bimonthly"
        or payroll_frequency == ""
    ):
        fiscal_year = get_fiscal_year(start_date, company=company)[0]
        month = "%02d" % getdate(start_date).month
        m = get_month_details(fiscal_year, month)
        if payroll_frequency == "Bimonthly":
            if getdate(start_date).day <= 15:
                start_date = m["month_start_date"]
                end_date = m["month_mid_end_date"]
            else:
                start_date = m["month_mid_start_date"]
                end_date = m["month_end_date"]
        else:
            start_date = m["month_start_date"]
            end_date = m["month_end_date"]

    if payroll_frequency == "Weekly":
        end_date = add_days(start_date, 6)

    if payroll_frequency == "Fortnightly":
        end_date = add_days(start_date, 13)

    if payroll_frequency == "Daily":
        end_date = start_date

    return frappe._dict({"start_date": start_date, "end_date": end_date})


def get_frequency_kwargs(frequency_name):
    frequency_dict = {
        "monthly": {"months": 1},
        "fortnightly": {"days": 14},
        "weekly": {"days": 7},
        "daily": {"days": 1},
    }
    return frequency_dict.get(frequency_name)


@frappe.whitelist()
def get_end_date(start_date, frequency):
    start_date = getdate(start_date)
    frequency = frequency.lower() if frequency else "monthly"
    kwargs = (
        get_frequency_kwargs(frequency)
        if frequency != "bimonthly"
        else get_frequency_kwargs("monthly")
    )

    end_date = add_to_date(start_date, **kwargs) - relativedelta(days=1)
    if frequency != "bimonthly":
        return dict(end_date=end_date.strftime(DATE_FORMAT))
    else:
        return dict(end_date="")


def get_month_details(year, month):
    ysd = frappe.db.get_value("Fiscal Year", year, "year_start_date")
    if ysd:
        diff_mnt = cint(month) - cint(ysd.month)
        if diff_mnt < 0:
            diff_mnt = 12 - int(ysd.month) + cint(month)
        msd = ysd + relativedelta(months=diff_mnt)
        month_days = cint(calendar.monthrange(cint(msd.year), cint(month))[1])
        mid_start = datetime.date(msd.year, cint(month), 16)
        mid_end = datetime.date(msd.year, cint(month), 15)
        med = datetime.date(msd.year, cint(month), month_days)
        return frappe._dict(
            {
                "year": msd.year,
                "month_start_date": msd,
                "month_end_date": med,
                "month_mid_start_date": mid_start,
                "month_mid_end_date": mid_end,
                "month_days": month_days,
            }
        )
    else:
        frappe.throw(_("Fiscal Year {0} not found").format(year))


@frappe.whitelist()
def create_log(ss_list):
    if not ss_list:
        frappe.throw(
            _(
                "There's no employee for the given criteria. Check that Salary Slips have not already been created."
            ),
            title="Error",
        )
    return ss_list


def format_as_links(salary_slip):
    return ['<a href="#Form/Salary Slip/{0}">{0}</a>'.format(salary_slip)]


def create_submit_log(submitted_ss, not_submitted_ss, jv_name):
    if not submitted_ss and not not_submitted_ss:
        frappe.msgprint(
            "No salary slip found to submit for the above selected criteria OR salary slip already submitted"
        )

    if not_submitted_ss:
        frappe.msgprint(
            "Could not submit any Salary Slip <br>\
            Possible reasons: <br>\
            1. Net pay is less than 0. <br>\
            2. Company Email Address specified in employee master is not valid. <br>"
        )


def get_salary_slip_list(name, docstatus, as_dict=0):
    payroll_entry = frappe.get_doc("Payroll Entry", name)

    salary_slip_list = frappe.db.sql(
        "select t1.name, t1.salary_structure from `tabSalary Slip` t1 "
        "where t1.docstatus = %s "
        "and t1.start_date >= %s "
        "and t1.end_date <= %s",
        (docstatus, payroll_entry.start_date, payroll_entry.end_date),
        as_dict=as_dict,
    )

    return salary_slip_list


@frappe.whitelist()
def payroll_entry_has_created_slips(name):
    response = {}

    draft_salary_slips = get_salary_slip_list(name, docstatus=0)
    submitted_salary_slips = get_salary_slip_list(name, docstatus=1)

    response["draft"] = 1 if draft_salary_slips else 0
    response["submitted"] = 1 if submitted_salary_slips else 0

    return response


def get_payroll_entry_bank_entries(payroll_entry_name):
    journal_entries = frappe.db.sql(
        "select name from `tabJournal Entry Account` "
        'where reference_type="Payroll Entry" '
        "and reference_name=%s and docstatus=1",
        payroll_entry_name,
        as_dict=1,
    )

    return journal_entries


@frappe.whitelist()
def payroll_entry_has_bank_entries(name):
    response = {}

    bank_entries = get_payroll_entry_bank_entries(name)
    response["submitted"] = 1 if bank_entries else 0

    return response
