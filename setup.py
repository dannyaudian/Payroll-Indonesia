from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in payroll_indonesia/__init__.py
from payroll_indonesia import __version__ as version

setup(
    name="payroll_indonesia",
    version=version,
    description="Payroll Indonesia - Modul Perhitungan BPJS & PPh 21 untuk ERPNext Indonesia",
    author="IMOGI",
    author_email="hello@imogi.tech",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires
)