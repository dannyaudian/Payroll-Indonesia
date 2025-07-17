# Contributing to Payroll Indonesia

This project relies on the Frappe Framework and ERPNext. To run the test suite locally you need a working bench environment with ERPNext installed.

## 1. Create a bench environment

```bash
# install bench if not already available
pip install frappe-bench

# create a new bench using the ERPNext 15 branch
bench init payroll-bench --frappe-branch version-15
cd payroll-bench

# fetch ERPNext
bench get-app erpnext --branch version-15
```

## 2. Create a site

```bash
bench new-site test.local
bench --site test.local install-app erpnext
```

## 3. Install Payroll Indonesia

Clone this repository inside your bench `apps` directory:

```bash
cd apps
git clone https://github.com/dannyaudian/payroll_indonesia.git
cd ..
bench --site test.local install-app payroll_indonesia
```

## 4. Run the tests

Activate developer mode so the site can run tests and then execute `pytest` through bench:

```bash
bench --site test.local set-config developer_mode 1
bench --site test.local run-tests --app payroll_indonesia
```

This command will launch `pytest` with Frappe's test runner so all tests in `payroll_indonesia/payroll_indonesia/tests` are executed against the created site.

## 5. Lint the code

Before committing your changes, install the linter and run it against the code base:

```bash
pip install flake8
flake8
```

Fix any reported issues prior to creating a pull request.


