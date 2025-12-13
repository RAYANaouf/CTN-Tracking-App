
import frappe
import json






@frappe.whitelist()
def get_items_from_ctns(ctn_list):
    """
    Accepts a list of CTN-BOX names.
    Returns a list of item the ctn contain with item_code, qty, uom, s_warehouse (gotten from the CTN warehouse).
    """
    item_map = {}
    
    if isinstance(ctn_list, str):
        ctn_list = json.loads(ctn_list)  # Deserialize from string to Python list if needed

    for ctn_name in ctn_list:
        ctn = frappe.get_doc("Carton", ctn_name)
        
        for row in ctn.items:
            item = frappe.get_doc("Item", row.item)
            uom = item.stock_uom or (item.uoms[0].uom if item.uoms else "")
            conversion_factor = 1.0
            
            
            # Find the conversion factor if stock_uom is not default
            if item.uoms:
                for uom_row in item.uoms:
                    if uom_row.uom == uom:
                        conversion_factor = uom_row.conversion_factor or 1.0
                        break
                    
                    
            key = (row.item, uom, ctn.warehouse)

                
            if key not in item_map:
                if not uom:
                    item_map[key] = {
                        "item_code": row.item,
                        "qty": 0,
                        "s_warehouse": ctn.warehouse
                    }
                else:
                    item_map[key] = {
                        "item_code": row.item,
                        "qty": 0,
                        "uom": uom,
                        "conversion_factor": conversion_factor,
                        "s_warehouse": ctn.warehouse
                    }
                    
            item_map[key]["qty"] += row.qty

    return list(item_map.values())








#################################### events #######################################
###################################################################################




#Stock Entry  event
#type = "Material Transfer"
#on submit , on cancel
def update_carton_warehouse(doc, method):
    """
    Update CTN Box warehouse on submit or cancel of Material Transfer.
    """
    if doc.stock_entry_type != "Material Transfer":
        return

    if not doc.get("custom_carton_table"):
        return

    if method == "on_submit":
        target_warehouse = doc.items[0].t_warehouse  # Assumes uniform target
    elif method == "on_cancel":
        target_warehouse = doc.items[0].s_warehouse  # Reset to source or set to None if needed
    else:
        return

    for row in doc.custom_carton_table:
        frappe.db.set_value("Carton", row.carton, "warehouse", target_warehouse)









#############################################################################################
#############################################################################################