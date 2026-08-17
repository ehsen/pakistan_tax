# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FBRSettings(Document):
	pass

class MockSettings:
	def __init__(self, env, token):
		self.environment = env
		self.name = "Unsaved FBR Settings"
		self.token = token
		self.provinces = []
		
	def get_password(self, field, raise_exception=False):
		return self.token

@frappe.whitelist()
def sync_provinces(env, token):
	from pakistan_tax.fbr.client import FBRClient
	from pakistan_tax.fbr.sync import sync_provinces as _sync
	
	settings = MockSettings(env, token)
	client = FBRClient(settings=settings)
	return _sync(client)
