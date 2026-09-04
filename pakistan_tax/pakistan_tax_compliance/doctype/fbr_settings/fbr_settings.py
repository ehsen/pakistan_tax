# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, get_url_to_form, now_datetime


class FBRSettings(Document):
	pass


@frappe.whitelist()
def fetch_tax_updates(company):
	"""Queue the full FBR sync for one company in the background: provinces
	first (every later reference/rate lookup is scoped by province code, so
	nothing downstream is worth attempting until that succeeds), then the
	rest of reference data and Item Tax Template generation — one connected
	sequence rather than separate manual buttons/steps. Runs independently
	of is_enabled so the pipeline can be dry-run before flipping it on for
	real automatic (daily) traffic.

	Returns immediately; the caller is notified via a Notification Log
	entry (desk bell icon) when the job finishes, success or failure."""
	frappe.only_for("System Manager")
	if not frappe.db.exists("FBR Settings", company):
		frappe.throw(_("No FBR Settings found for company {0}").format(company))

	frappe.enqueue(
		"pakistan_tax.pakistan_tax_compliance.doctype.fbr_settings.fbr_settings.run_tax_update_sync",
		queue="long",
		job_name=f"fbr-fetch-tax-updates-{company}",
		company=company,
		requested_by=frappe.session.user,
	)
	return {"queued": True}


def run_tax_update_sync(company, requested_by=None):
	"""Background worker for fetch_tax_updates — see that docstring for the
	provinces-then-tax-data sequencing rationale."""
	from pakistan_tax.fbr.client import FBRClient
	from pakistan_tax.fbr.sync import (
		sync_provinces, sync_transaction_types, sync_uoms, sync_rates, sync_sro_chain)
	from pakistan_tax.tax_config.template_generator import setup_company_tax_config

	settings = frappe.get_doc("FBR Settings", company)
	client = FBRClient(settings=settings)
	out = {}

	try:
		out["provinces"] = sync_provinces(client)
	except Exception:
		_finish(company, requested_by, "Failed",
			"Province sync failed — tax data was not fetched.\n" + frappe.get_traceback())
		return

	try:
		out["transaction_types"] = sync_transaction_types(client)
		out["uoms"] = sync_uoms(client)
		out["rates"] = sync_rates(client)
		out["sro"] = sync_sro_chain(client)
		out["tax_config"] = setup_company_tax_config(company)
	except Exception:
		_finish(company, requested_by, "Failed", frappe.get_traceback())
		return

	_finish(company, requested_by, "Success", _summarize_sync(out))


def _finish(company, requested_by, status, summary):
	frappe.db.set_value("FBR Settings", company, {
		"last_sync_on": now_datetime(),
		"last_sync_status": status,
		"last_sync_summary": summary[:1000],
	}, update_modified=False)

	if requested_by:
		_notify(requested_by, company, status, summary)

	frappe.db.commit()


def _notify(user, company, status, summary):
	subject = (
		_("FBR tax updates fetched for {0}").format(company) if status == "Success"
		else _("FBR tax update fetch failed for {0}").format(company)
	)
	frappe.get_doc({
		"doctype": "Notification Log",
		"subject": subject,
		"email_content": f"<pre>{escape_html(summary[:1000])}</pre>",
		"for_user": user,
		"type": "Alert",
		"document_type": "FBR Settings",
		"document_name": company,
		"link": get_url_to_form("FBR Settings", company),
	}).insert(ignore_permissions=True)


def _summarize_sync(out):
	parts = []
	if "provinces" in out:
		parts.append(f"provinces: +{out['provinces'].get('inserted', 0)}")
	for key in ("transaction_types", "uoms"):
		if key in out:
			parts.append(f"{key}: +{out[key].get('inserted', 0)}")
	if "rates" in out:
		r = out["rates"]
		parts.append(f"rates: opened {r.get('opened', 0)}/closed {r.get('closed', 0)}")
	itt = out.get("tax_config", {}).get("item_tax_templates", {})
	if itt:
		parts.append(f"item tax templates: +{itt.get('created', 0)}")
	return "Tax updates fetched — " + ", ".join(parts) if parts else "Tax updates fetched."
