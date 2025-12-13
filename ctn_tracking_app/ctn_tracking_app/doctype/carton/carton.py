# Copyright (c) 2025, rayan aouf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Carton(Document):
	pass



@frappe.whitelist()
def get_transactions(carton_name):
	return frappe.db.get_list(
    	"Carton Transaction",
        filters={"carton": carton_name, "docstatus": 1},
        fields=["*"]  
    )