import frappe
from erpnext.accounts.utils import get_account_currency
from frappe.utils import add_days, cint, cstr, flt, formatdate, get_link_to_form, getdate, nowdate
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice




class CustomSalesInvoice(SalesInvoice):
	def get_gl_entries(self, warehouse_account=None):
		from erpnext.accounts.general_ledger import merge_similar_entries

		gl_entries = []

		self.make_customer_gl_entry(gl_entries)

		self.make_tax_gl_entries(gl_entries)
		self.make_internal_transfer_gl_entries(gl_entries)

		self.make_item_gl_entries(gl_entries)
		disable_sdbnb_in_sr = frappe.db.get_value("Company", self.company, "disable_sdbnb_in_sr")
		if not self.is_return:
			self.stock_delivered_but_not_billed_gl_entries(gl_entries)
		else:
			if not disable_sdbnb_in_sr:
				stock_delivered_but_not_billed_gl_entries(gl_entries)

		self.make_precision_loss_gl_entry(gl_entries)
		self.make_discount_gl_entries(gl_entries)

		# merge gl entries before adding pos entries
		gl_entries = merge_similar_entries(gl_entries)

		self.make_loyalty_point_redemption_gle(gl_entries)
		self.make_pos_gl_entries(gl_entries)

		self.make_write_off_gl_entry(gl_entries)
		self.make_gle_for_rounding_adjustment(gl_entries)

		return gl_entries

	def stock_delivered_but_not_billed_gl_entries(self, gl_entries):
		if not self.update_stock:
			for item in self.get("items"):
				if item.delivery_note and item.dn_detail:
					is_stock_item = frappe.db.get_value("Item", item.item_code, "is_stock_item")
					if not is_stock_item:
						dn_expense_account = frappe.db.get_value("Delivery Note Item", item.dn_detail, "expense_account")
						if dn_expense_account and dn_expense_account != item.expense_account:
							item_g = frappe.db.get_value("Stock Ledger Entry",
								{
									"voucher_no": item.delivery_note,
									"voucher_detail_no": item.dn_detail,
									"item_code": item.item_code
								},
								["stock_value_difference", "actual_qty"]
							,as_dict = True)
							valuation_rate = item_g.stock_value_difference / item_g.actual_qty
							valuation_amount = valuation_rate * item.stock_qty
							account_currency = get_account_currency(dn_expense_account)
							gl_entries.append(
								self.get_gl_dict(
									{
										"account": dn_expense_account,
										"against": item.expense_account,
										"credit": flt(valuation_amount),
										"credit_in_account_currency": (
											flt(valuation_amount)
										),
										"cost_center": item.cost_center,
									},
									account_currency,
									item=item,
								)
							)
							gl_entries.append(
								self.get_gl_dict(
									{
										"account": item.expense_account,
										"against": dn_expense_account,
										"debit": flt(valuation_amount),
										"debit_in_account_currency": (
											flt(valuation_amount)
										),
										"cost_center": item.cost_center,
									},
									account_currency,
									item=item,
								)
							)
