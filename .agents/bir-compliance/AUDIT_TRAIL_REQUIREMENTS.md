# Audit Trail Strict Requirements and Features
## 1. Statutory Reference Matrix (Lookup when in doubt)
- **Source:** bir-docs/Annex B_STANDARD FUNCTIONAL REQUIREMENTS.docs
- **Electronic Invoicing Policies**: `bir-docs/RMC No. 98-2026 redacted.pdf`
- **EIS API & Transmission Specs**: `bir-docs/EIS e-invoice API Development Guide for PILOT.pdf`
- **EIS JSON Payload Fields & Codes**: `bir-docs/e-Invoice JSON File Format.xlsx` & `bir-docs/cas_mapping_template.json`
- **Books of Accounts & Exports**: RR No. 9-2009 (Mandatory Fields), RR No. 16-2006 (`.csv`/`.dat` formats)
- **Data Retention Period**: RR No. 17-2013 as amended by RR No. 5-2014 (10-year retention)

## 2. Annex B Summary
**Item 8** is a printable activity log, the thing I described earlier.
**Items 10** and **11.i** are integrity rules for transactions: numbering, dates, immutability and balance checks. These are really **“tamper-proof bookkeeping”** rules, and they affect your core data model more than the log does.

## 3. Audit Trail Definition as per BIR Annex B
### 10.a System controls receipt numbering

- **Plain meaning:** users can’t type or choose the invoice or receipt number. The system assigns it.

- **SE view:** assign the number server-side, inside the posting transaction, from a counter per document series. Don’t accept it in the request body. Use a counter row with `SELECT … FOR UPDATE`, not a bare Postgres sequence, because sequences skip numbers when a transaction rolls back and BIR will ask about gaps. Check that the number is inside the series range from the Acknowledgment Certificate, and refuse to issue beyond it. A voided document still consumes its number.

### 10.b Posting date = date it entered the system

- **Plain meaning:** the recorded date of entry is the real one, not something a user can set or backdate.

- **SE view:** a `posted_at` column set by the DB (`DEFAULT now()`) and never accepted from the client. Keep it separate from the business dates (`IssueDtm`, transaction date), which a user can legitimately pick. Make `posted_at` immutable. The EIS also validates that issuance isn’t after transmission (`ERR002`).

### 10.c Voidable, not modifiable once posted

- **Plain meaning:** a posted transaction can’t be edited. A mistake is fixed by cancelling it and recording a new one.

- **SE view:** a status model (`draft → posted → voided`). Drafts are editable, and posted rows are not. Enforce it in three layers: the API has no edit endpoint for posted docs, the service layer rejects it, and a DB trigger raises an error on UPDATE of business columns after posting. A void records `voided_by`, `voided_at` and a mandatory `reason`, and writes reversing ledger entries, so the original stays visible. Check how a void interacts with a document already accepted by the EIS. A credit memo may be the correct route, not a void.

### 10.d Run date = date the report was generated

- **Plain meaning:** a report shows when it was produced, not a date chosen by the user.

- **SE view:** stamp every report with the `server’s current time`. Keep it separate from the report’s period (`from/to dates`, which are user inputs). It’s one field in a shared report header, together with the other required stamps (software name and version, user ID).

### 10.e No editing of generated reports, and no overriding edits in the programs

- **Plain meaning:** two things. Reports are read-only. And “edits” here means edit checks, an old term for input validation. The rule says users can’t bypass validation rules.
- **SE view:**

  - Reports are generated server-side as PDF or CSV, with no edit UI. For extra trust, stamp each with a report ID and log the generation in the audit log.

  - No `force=true` flags, no “admin edit posted record” endpoints, no role that skips validation. Validation lives in the service layer and DB constraints, and no one gets a bypass.

### 10.f The system prevents users from having the capability to override edits within computer programs;

- **Plain meaning:** Refer to 10.c

### 10.g Every record stamped with the creating user’s ID

- **Plain meaning:** you can always tell who created a record.

- **SE view:** `created_by` (`NOT NULL`, foreign key to users) on every business table, `taken from the authenticated session, never from the request body`. Add `posted_by` and `voided_by` as well. Because users are deactivated and never deleted, these references stay valid.

### 10.h Automatic totals and cross-checks, reporting out-of-balance conditions

- **Plain meaning:** the system calculates totals itself and catches inconsistencies.
- **SE view:**

  - Recompute invoice totals and VAT on the server from line items. Never trust totals sent by the client.

  - At posting, check that debits equal credits and reject the transaction if not.

  - Add periodic reconciliation checks: sales journal total against the GL sales account, subledgers against control accounts, trial balance totals.

  - Provide a visible “out-of-balance report” (or dashboard flag) that lists any failures. A scheduled job that runs these checks and logs the results is a straightforward way to satisfy the “report” part.

  - Use Decimal and fixed-precision DB types throughout, because float rounding is a classic source of one-cent imbalances.

- **Note:** This is both Audit Trail and System Nature requirements, but they’re different layers. For this build, treat it as a mandatory requirement that you implement as part of the core system, not as part of the audit log feature.

### 11.i Audit trails protected from modification and destruction

- **Plain meaning:** no one, including admins, can change or delete the log.
- **SE view:** an append-only `audit_log`. The app’s DB role has no `UPDATE, DELETE, TRUNCATE or DROP` on it. Add a `hash chain` (each row stores a hash of the previous one) so tampering is detectable.
