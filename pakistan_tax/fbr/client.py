# Copyright (c) 2026, SpotLedger
"""Thin transport layer for all FBR API calls.

Every call is logged to `FBR Api Log`. Responses are parsed as JSON
regardless of HTTP status code — some FBR endpoints (e.g. Get_Reg_Type)
return a valid JSON body with HTTP 500.
"""

import json

import frappe
import requests
from frappe import _

PDI_V1 = "https://gw.fbr.gov.pk/pdi/v1"
PDI_V2 = "https://gw.fbr.gov.pk/pdi/v2"
DIST_V1 = "https://gw.fbr.gov.pk/dist/v1"
DI_DATA = "https://gw.fbr.gov.pk/di_data/v1/di"

REQUEST_TIMEOUT = 30


class FBRResponse:
	def __init__(self, status_code, data, text=""):
		self.status_code = status_code
		self.data = data  # parsed JSON (dict/list) or None
		self.text = text

	@property
	def ok(self):
		return self.status_code == 200 and self.data is not None


def get_settings(company=None):
	"""Return the enabled FBR Settings doc for a company (or the first enabled one)."""
	filters = {"is_enabled": 1}
	if company:
		filters["company"] = company
	name = frappe.db.get_value("FBR Settings", filters, "name")
	if not name:
		frappe.throw(_("No enabled FBR Settings found{0}").format(
			_(" for company {0}").format(company) if company else ""))
	return frappe.get_doc("FBR Settings", name)


class FBRClient:
	def __init__(self, company=None, settings=None):
		self.settings = settings or get_settings(company)

	def get_token(self):
		field = "sandbox_token" if self.settings.environment == "Sandbox" else "production_token"
		token = self.settings.get_password(field, raise_exception=False)
		if not token:
			frappe.throw(_("{0} not configured in FBR Settings {1}").format(
				field, self.settings.name))
		return token

	def _headers(self, json_body=False):
		headers = {
			"Authorization": f"Bearer {self.get_token()}",
			"Accept": "application/json",
		}
		if json_body:
			headers["Content-Type"] = "application/json"
		return headers

	def get(self, url, params=None, reference_doctype=None, reference_name=None):
		return self._request("GET", url, params=params,
			reference_doctype=reference_doctype, reference_name=reference_name)

	def post(self, url, payload=None, reference_doctype=None, reference_name=None):
		return self._request("POST", url, payload=payload,
			reference_doctype=reference_doctype, reference_name=reference_name)

	def _request(self, method, url, params=None, payload=None,
			reference_doctype=None, reference_name=None):
		status_code, data, text, error = 0, None, "", None
		try:
			if method == "GET":
				resp = requests.get(url, params=params, headers=self._headers(),
					timeout=REQUEST_TIMEOUT)
			else:
				resp = requests.post(url, json=payload, headers=self._headers(json_body=True),
					timeout=REQUEST_TIMEOUT)
			status_code, text = resp.status_code, resp.text
			try:
				data = resp.json()
			except ValueError:
				data = None
		except requests.RequestException as e:
			error = str(e)

		self._log(method, url, params or payload, status_code, data, text, error,
			reference_doctype, reference_name)

		if error:
			return FBRResponse(0, None, error)
		return FBRResponse(status_code, data, text)

	def _log(self, method, url, request_payload, status_code, data, text, error,
			reference_doctype, reference_name):
		try:
			frappe.get_doc({
				"doctype": "FBR Api Log",
				"endpoint": url,
				"method": method,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"status_code": status_code,
				"success": 1 if (status_code == 200 and not error) else 0,
				"error_summary": error or (text[:500] if status_code != 200 else None),
				"request_payload": json.dumps(request_payload, indent=1, default=str)
					if request_payload else None,
				"response_payload": json.dumps(data, indent=1, default=str)
					if data is not None else (text[:5000] or None),
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="FBR Api Log insert failed",
				message=f"{method} {url}\n{frappe.get_traceback()}")

	# ---------------- Reference API wrappers (doc section 5) ----------------

	def provinces(self):
		return self.get(f"{PDI_V1}/provinces")

	def doc_type_codes(self):
		return self.get(f"{PDI_V1}/doctypecode")

	def transaction_types(self):
		return self.get(f"{PDI_V1}/transtypecode")

	def uoms(self):
		return self.get(f"{PDI_V1}/uom")

	def sale_type_to_rate(self, date_dd_mon_yyyy, trans_type_id, province_code):
		return self.get(f"{PDI_V2}/SaleTypeToRate", params={
			"date": date_dd_mon_yyyy,
			"transTypeId": trans_type_id,
			"originationSupplier": province_code,
		})

	def sro_schedule(self, rate_id, date_dd_mon_yyyy, province_code):
		return self.get(f"{PDI_V1}/SroSchedule", params={
			"rate_id": rate_id,
			"date": date_dd_mon_yyyy,
			"origination_supplier_csv": province_code,
		})

	def sro_items(self, date_iso, sro_id):
		return self.get(f"{PDI_V2}/SROItem", params={"date": date_iso, "sro_id": sro_id})

	def hs_uom(self, hs_code, annexure_id=3):
		return self.get(f"{PDI_V2}/HS_UOM", params={
			"hs_code": hs_code, "annexure_id": annexure_id})

	def statl(self, regno, date_iso):
		return self.post(f"{DIST_V1}/statl", payload={"regno": regno, "date": date_iso})

	def get_reg_type(self, regno):
		return self.post(f"{DIST_V1}/Get_Reg_Type", payload={"Registration_No": regno})
