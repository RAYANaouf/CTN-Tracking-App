# Copyright (c) 2025, rayan aouf and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class Carton(Document):
	def validate(self):
		if self.is_new():
			return

		previous_verified = frappe.db.get_value("Carton", self.name, "verified")
		if self.verified and not previous_verified and not self.flags.get("from_verify"):
			frappe.throw("Use the Verify Carton button on an Opened carton.")

		if previous_verified:
			self._lock_packing_list()

	def _lock_packing_list(self):
		previous = {
			row.name: row
			for row in frappe.get_all(
				"Carton Item",
				filters={"parent": self.name},
				fields=["name", "item", "qty"],
			)
		}
		current_names = {row.name for row in (self.items or []) if row.name}
		if set(previous) != current_names or len(self.items or []) != len(previous):
			frappe.throw("The carton quantity cannot be changed after verification.")

		for row in self.items or []:
			prev = previous.get(row.name)
			if not prev or prev.item != row.item or flt(prev.qty) != flt(row.qty):
				frappe.throw("The carton quantity cannot be changed after verification.")

@frappe.whitelist()
def get_transactions(carton_name):
	return frappe.db.get_list(
		"Carton Transaction",
		filters={"carton": carton_name, "docstatus": 1},
		fields=["*"],
	)


@frappe.whitelist()
def verify_carton(carton_name, lines):
	if isinstance(lines, str):
		lines = json.loads(lines or "[]")

	doc = frappe.get_doc("Carton", carton_name)
	if not frappe.has_permission("Carton", "write", doc):
		frappe.throw("Not permitted to verify this carton.", frappe.PermissionError)

	if doc.verified:
		frappe.throw("This carton is already verified.")
	if doc.status != "Opened":
		frappe.throw("Set the carton status to Opened before verifying it.")

	packing = {}
	for row in doc.items or []:
		if row.item:
			packing[row.item] = packing.get(row.item, 0) + flt(row.qty)

	counted = {}
	for line in lines or []:
		item = line.get("item")
		if not item:
			continue
		if item in counted:
			frappe.throw(f"Item {item} is listed more than once. Edit the counted quantity on its packing line.")
		qty = flt(line.get("counted_qty"))
		if qty < 0:
			frappe.throw(f"Counted quantity for {item} cannot be negative.")
		counted[item] = qty

	missing = [item for item in packing if item not in counted]
	if missing:
		frappe.throw("Count every packing list item: " + ", ".join(missing))

	rows = []
	receipt_totals = {}
	issue_totals = {}
	for item in sorted(set(packing) | set(counted)):
		packing_qty = flt(packing.get(item))
		counted_qty = flt(counted.get(item))
		difference = counted_qty - packing_qty
		rows.append(
			{
				"item": item,
				"packing_qty": packing_qty,
				"counted_qty": counted_qty,
				"difference": difference,
			}
		)
		if difference > 0:
			receipt_totals[item] = difference
		elif difference < 0:
			issue_totals[item] = abs(difference)

	receipt = None
	issue = None
	if receipt_totals:
		receipt = _make_stock_entry(
			"Material Receipt",
			doc.company,
			doc.warehouse,
			receipt_totals,
			f"Extra quantity found in carton {doc.name}",
			incoming=True,
		)
	if issue_totals:
		issue = _make_stock_entry(
			"Material Issue",
			doc.company,
			doc.warehouse,
			issue_totals,
			f"Missing quantity in carton {doc.name}",
			incoming=False,
		)

	_apply_counted_quantities(doc, counted)

	doc.flags.from_verify = True
	doc.verified = 1
	doc.verified_by = frappe.session.user
	doc.verified_on = now_datetime()
	doc.verification_receipt = receipt.name if receipt else None
	doc.verification_issue = issue.name if issue else None
	doc.save(ignore_permissions=True)

	return {
		"receipt": receipt.name if receipt else None,
		"issue": issue.name if issue else None,
	}


def _apply_counted_quantities(doc, counted):
	"""Replace the packing-list qty with the counted qty so the carton HTML uses it."""
	seen = set()
	for row in doc.items or []:
		if not row.item:
			continue
		if row.item in seen:
			row.qty = 0
			continue
		seen.add(row.item)
		row.qty = flt(counted.get(row.item, 0))

	for item, qty in counted.items():
		if item not in seen:
			doc.append("items", {"item": item, "qty": flt(qty)})


def _make_stock_entry(stock_entry_type, company, warehouse, totals, remarks, incoming):
	entry = frappe.new_doc("Stock Entry")
	entry.stock_entry_type = stock_entry_type
	entry.company = company
	entry.remarks = remarks
	if incoming:
		entry.to_warehouse = warehouse
	else:
		entry.set_warehouse = warehouse

	for item_code, qty in totals.items():
		line = {
			"item_code": item_code,
			"qty": qty,
			"company": company,
			"description": remarks,
		}
		if incoming:
			line["t_warehouse"] = warehouse
		else:
			line["s_warehouse"] = warehouse
		entry.append("items", line)

	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry
