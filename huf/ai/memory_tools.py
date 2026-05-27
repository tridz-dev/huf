import json

import frappe


def ping():
    return {"ok": True, "v": 2}
