import frappe
from packaging.version import Version

def is_frappe_16():
    major_version = int(frappe.__version__.split(".", 1)[0])
    return major_version >= 16