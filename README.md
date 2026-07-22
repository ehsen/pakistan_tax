# Pakistan Tax Compliance

End-to-end Pakistan tax compliance for ERPNext — FBR Digital Invoicing, native
ERPNext tax-engine configuration, withholding tax, and party-level tax
reconciliation.

This app is a from-scratch rebuild of two earlier apps (`taxcompliancepakistan`
and `fbr_digital_invoicing`) around one core principle: **it never overrides
ERPNext's tax calculation**. Sales Tax, Further Tax, Advance Tax (236G), fixed
and compound FBR rates, and 3rd Schedule goods are all modeled as native Item
Tax Templates, Tax Rules, and Sales/Purchase Taxes and Charges rows — the
built-in `calculate_taxes_and_totals` engine does the math, exactly as it does
for every other ERPNext user. What this app adds is Pakistan-specific
*configuration* of that engine, plus everything the tax engine itself can't
provide: FBR reference-data sync, Digital Invoicing API integration, and a
party-level tax subledger for reconciliation.

## Requirements

| Dependency | Minimum version | Why |
|---|---|---|
| [Frappe](https://github.com/frappe/frappe) | v16.0.0 | Dated Item Tax template selection, the `Item Wise Tax Detail` child table, and regional GL hooks this app relies on were introduced/changed in v16 |
| [ERPNext](https://github.com/frappe/erpnext) | v16.0.0 | Same as above — this app is a regional configuration layer on top of ERPNext's own accounts/tax engine |
| ERPNext Accounts module (**Payment Entry**) | — | Withholding tax (WHT) is calculated on Payment Entry submission via native Advance Taxes and Charges rows — Payment Entry must be enabled/reachable in the site |

Installing on Frappe/ERPNext v15 or earlier is blocked by a `before_install`
check with a clear error message rather than failing silently later.

## What it does

- **Native tax engine configuration** — Item Tax Templates generated per
  (FBR transaction type, FBR rate), including split-account handling for
  compound rates (e.g. *"18% along with rupees 60 per kilogram"*) and
  per-quantity fixed rates via `On Item Quantity` charge rows.
- **Dated FBR reference data** — provinces, transaction types, rates, SROs
  and SRO items are synced from FBR's reference APIs and kept as
  interval-dated records (snapshot-diff), so historical and backdated
  invoices resolve the rate that was actually in force on their date.
- **FBR Digital Invoicing** — payload construction from frozen invoice
  snapshots, `validateinvoicedata`/`postinvoicedata` (sandbox and
  production), API call logging, and SRO Applicability for goods-level and
  buyer-level concessions (zero-rating, DTRE, EFS, etc.).
- **Withholding tax** — filer/non-filer rates by WHT section, calculated on
  Payment Entry through native tax rows (no core GL overrides).
- **Party-level tax subledger** — a `Tax Ledger Entry` doctype tracks input
  tax claims against Annex-A supplier declarations, WHT withheld-by-us and
  withheld-from-us positions, CPR deposits and certificates, and
  month-end sales tax return settlement — answering "who owes whom what"
  at the party level, which plain GL balances can't.
- **Reports** — Annex C, Tax Divergence, Input Tax Reconciliation, and
  Supplier WHT Certificate.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/ehsensiraj/pakistan_tax --branch develop
bench install-app pakistan_tax
```

Use `--branch main` once a tagged release is available; `develop` tracks
active development.

## Branches

- **`main`** — stable, released code. Tagged versions will be cut from here
  once CI/CD is set up.
- **`develop`** — active development target for all feature work; open pull
  requests against this branch.

## Status

This app is under active development and has been exercised end-to-end
against FBR's sandbox environment, but has not yet had a tagged release or
been run in production. Review the code and test thoroughly in your own
sandbox before relying on it for live filings.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please
[install pre-commit](https://pre-commit.com/#installation) and enable it for
this repository:

```bash
cd apps/pakistan_tax
pre-commit install
```

Pre-commit is configured to use the following tools for checking and
formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

## License

MIT
