# Payroll Indonesia

Payroll Indonesia by PT. Innovasi Terbaik Bangsa is an ERPNext v15 payroll module specifically designed for Indonesian companies. This module is modular, scalable, and compatible with both VPS and Frappe Cloud.

## 🚀 Key Features

* **🛠 ERPNext HRM Integration:** Fully integrated with Salary Component, Salary Structure, Salary Slip, Payroll Entry, Employee Tax Summary, and Payroll Indonesia Settings modules.
* **💡 Automated BPJS Calculation:** Automatic calculation of BPJS Kesehatan (Healthcare) and Ketenagakerjaan (Employment Security - JHT, JP, JKK, JKM) complying with the latest regulations, with validation for contribution percentages and maximum salary limits.
* **📊 PPh 21 Calculation:** Supports TER (PMK 168/2023) and monthly progressive methods, special calculations for December for annual SPT reporting, including validation for PTKP and Tax Bracket settings.
* **⚡ Memory Optimization:** Efficient YTD and YTM calculations, comprehensive error handling to manage RAM usage, and complete integration with dedicated calculation modules.

## 📦 Installation

### ✅ Prerequisites

* ERPNext v15
* Frappe Framework v15

### 📌 Installation via GitHub

```bash
bench get-app https://github.com/dannyaudian/payroll_indonesia
bench --site your_site.local install-app payroll_indonesia
bench migrate
```

### 🛠 Initial Setup

1. **🔄 Database Migration:** Run the database migration before setup:

```bash
bench --site your_site.local migrate
```

2. **⚙ Manual Setup After Installation:**

```bash
bench --site your_site.local execute payroll_indonesia.fixtures.setup.after_install
```

or via bench console:

```python
from payroll_indonesia.fixtures import setup
setup.after_install()
```

## 📝 Required Configuration

### 🔧 Payroll Indonesia Settings

* Customize basic Payroll Indonesia settings including tax calculation methods, BPJS contributions, PTKP, and TER configurations.
* Validation ensures configuration values are within allowed ranges.

### 📌 BPJS Account Mapping

* Use the **BPJS Account Mapping** DocType to set up BPJS Employee and Employer accounts.
* Ensure account configurations align with the company's Chart of Accounts structure.

### 📐 PPh 21 Settings

* Access **PPh 21 Settings**.
* Select calculation methods: Progressive or TER.
* Complete the PTKP table, Tax Bracket table (for Progressive), or TER table.

### 📑 Default Salary Structure

* Automatically available default salary structure named **"Struktur Gaji Tetap G1"**.
* Earnings and deductions components comply with standard Indonesian regulations (BPJS, PPh21).

## 📅 Payroll Period

Each Payroll Entry in ERPNext must belong to a defined **Payroll Period**. If you get validation errors that the Payroll Period is missing or out of range, create one first.

1. Open **Payroll Period** list via **HR > Payroll > Payroll Period**.
2. Click **New**, set the Start Date and End Date, then Save.
3. Select this Payroll Period when creating your Payroll Entry.

For more details, see the [Payroll Period documentation](https://docs.erpnext.com/docs/user/manual/en/payroll/payroll-period).

## 🔄 Optimization and Revision

The Payroll Indonesia module is modularly optimized to provide top performance and maintain a clear, integrated code structure across modules such as BPJS Settings, PPh21 Settings, Salary Slip, Employee Tax Summary, and Payroll Indonesia Settings. All configurations adhere to current standards, ensuring accuracy in calculations and validations.

## 📁 Module Structure

* **📋 Payroll Entry:** Enhanced validation, automated Salary Slip integration.
* **📃 Salary Slip:** Modular overrides for BPJS and PPh21 salary calculations.
* **📊 Salary Structure:** Wildcard company ('%') functionality, automatic GL account mappings.
* **👥 Employee & Auth Hooks:** Robust employee data validation, Indonesian region-specific user session integration.
* **📈 Employee Tax Summary:** Automated YTD calculation, comprehensive annual tax summaries per employee.
* **🛡 BPJS Settings & PPh 21 Settings:** Robust validation for contribution settings, salary limits, and automatic synchronization with central configurations.

## 🛠️ Technical Notes

* All code adheres to Flake8 standards and Pythonic best practices.
* Efficient and clear logging using Python’s logging module.
* Modular design featuring specialized utilities for BPJS, PPh21, YTD calculations, and field validations.

## 📢 Status

Actively developed and deployed across diverse production environments. For issue reporting and feature requests, visit our [GitHub Repository](https://github.com/dannyaudian/payroll_indonesia).

---

✨ **Last updated:** July 2025
