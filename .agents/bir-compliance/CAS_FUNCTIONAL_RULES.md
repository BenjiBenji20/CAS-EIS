# BIR CAS (Computerized Accounting System) Functional & Technical Rules

When designing, implementing, refactoring, or reviewing backend services, schemas, and accounting modules in this CAS (with EIS submodule), you MUST strictly enforce the following BIR-mandated technical invariants. If uncertain on specific field schemas or legal phrasing, consult the reference documents in `bir-docs/`.

---

## 1. Statutory Reference Matrix (Lookup when in doubt)
- **General CAS Functional Specs**: `bir-docs/Annex B_STANDARD FUNCTIONAL REQUIREMENTS.docx`
- **Electronic Invoicing Policies**: `bir-docs/RMC No. 98-2026 redacted.pdf`
- **EIS API & Transmission Specs**: `bir-docs/EIS e-invoice API Development Guide for PILOT.pdf`
- **EIS JSON Payload Fields & Codes**: `bir-docs/e-Invoice JSON File Format.xlsx` & `bir-docs/cas_mapping_template.json`
- **Books of Accounts & Exports**: RR No. 9-2009 (Mandatory Fields), RR No. 16-2006 (`.csv`/`.dat` formats)
- **Data Retention Period**: RR No. 17-2013 as amended by RR No. 5-2014 (10-year retention)

---

## 2. Transaction Immutability & Document Adjustments
- **Zero In-Place Mutation**: Once an accounting entry or invoice is `POSTED` / finalized, it CANNOT be modified, updated, or deleted (*Annex B Line 192*).
- **Enforcement**: Enforce immutability via database-level triggers/constraints or strict application-level guardrails.
- **Adjustments**: Decreases to sales/revenue MUST be made strictly via a standalone **Credit Note/Memo** referencing the original document (*RMC 98-2026 §IV.8*). Increases require a new distinct invoice.
- **Voiding**: Transactions may be voided only via reversing journal entries. Historical records remain preserved.

---

## 3. System-Controlled Sequential Numbering & Timestamps
- **System Control**: Receipt/invoice serial numbers must be strictly system-generated, gap-free/audited, and formatted with at least six (6) running digits padded with leading zeros (e.g., `INV-000001`) (*Annex B Lines 17, 188*).
- **Posting Date**: Must automatically capture the exact system entry timestamp when the transaction enters the system; backdating posted records is strictly forbidden (*Annex B Line 190*).
- **Reprint Handling**: Any subsequent printout of an existing receipt/invoice must conspicuously display the word **"REPRINT"** (*Annex B Line 71*).

---

## 4. Invoice Face & Mixed-Tax Computations
- **Header & Taxpayer Info**: Registered Name, Business Style, Registered Address, `VAT REG TIN` / `NON-VAT REG TIN` (9-digit TIN + 5-digit Branch Code) (*Annex B Lines 8–16*).
- **Mixed Transactions Breakdown**: Invoices containing mixed lines must explicitly itemize:
  `VATable Sales`, `VAT Amount (12%)`, `VAT Exempt Sales`, and `Zero-Rated Sales` (*Annex B Lines 40–48*). Purely exempt transactions must state **"EXEMPT"** prominently.
- **Discounts & Exemptions**: SC/PWD transactions require SC/PWD TIN/ID, detailed 20% + 12% VAT exemption calculation, and signature space (*Annex B Lines 51–59*). // check in the future if available to our company's business model.
- **Mandatory Footers**: Valid AC Number, Date Issued, Series Range, and required 5-year validity / Input Tax disclaimer texts (*Annex B Lines 60–70*).

---

## 5. Audit Trail & Logging Protocol
- **Append-Only Logging**: Every mutation, privilege change, and transaction creation must append to an unalterable, non-deletable audit trail (*Annex B Lines 177, 223, 245*).
- **Mandatory Audit Fields**: `timestamp` (system clock), `user_id`, `action_performed`, `record_id`, `old_values` (JSON), `new_values` (JSON), and `ip_address`.
- **User Stamping**: Every transaction record must permanently store the `user_id` of the creator (*Annex B Line 200*).
- **Out-of-Balance Detection**: The system must automatically cross-check debits vs. credits / invoice math and actively block or flag out-of-balance transactions (*Annex B Line 202*).

---

## 6. System Security & Access Control
- **Password Policies**: Require alphanumeric combination (*Annex B Line 216*); enforce mandatory password change every thirty (30) days (*Annex B Line 211*).
- **Lockout & Concurrency**: Deactivate/lock user accounts after consecutive failed sign-on attempts (*Annex B Line 209*). Strictly prevent simultaneous active sessions for the same user code across multiple terminals/browsers (*Annex B Line 207*).
- **Role-Based Access (RBAC)**: Non-admin users must be restricted from accessing OS commands, direct DB queries, or program edit overrides (*Annex B Lines 214, 219*).

---

## 7. Books of Accounts & Reporting (RR 9-2009 & RR 16-2006)
- **Mandatory Books**: System must generate **General Journal**, **General Ledger**, **Sales Journal**, **Purchase Journal**, and **Inventory Book** containing all statutory columns (*Annex B Lines 76–157*).
- **Report Headers**: Every report must include Taxpayer Name, Registered Address, TIN + Branch Code, Software Name & Version, Generating User ID, and Exact Generation Timestamp (`run_date`) (*Annex B Lines 158–170, 194*).
- **Export Formats**: Must support automated export of Books of Accounts and reports to **`.csv`** or **`.dat`** file formats (*Annex B Line 171*).
- **Withholding Tax Certificates**: Must support generation of **BIR Form 2306**, **BIR Form 2307**, and **BIR Form 2316** (*Annex B Lines 179–186*).

---

## 8. EIS Submodule Integration & Sales Reporting
- **Automated Transmission**: Posted sales transactions must be capable of generating and transmitting structured JSON payloads to the BIR EIS API (*RMC 98-2026 §IV.4-6*, `bir-docs/e-Invoice JSON File Format.xlsx`).
- **Correction Handling**: Use `CorrYN`, `CorrectionCd`, and `PrevUniqueId`. If correcting a pre-EIS invoice, set `PrevUniqueId` to 24 zeros (`000000000000000000000000`).
- **Invoice Splitting**: If a transaction mixes VATable, Zero-Rated, and Exempt items, split or classify items accurately per EIS transmission rules before submission.
- **Permit Metadata**: Maintain valid Permit to Use (`PTU`) / Acknowledgment Certificate (`AC`) / Permit to Issue (`PTI`) identifiers in payloads.

---

## 9. Data Retention & Archival
- Maintain database backups, financial logs, and transaction history for a mandatory period of **ten (10) years** (*RR 17-2013 / RR 5-2014, Annex B Line 175*).
