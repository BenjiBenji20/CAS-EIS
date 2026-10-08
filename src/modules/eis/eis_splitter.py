from decimal import Decimal
from typing import Dict, List, Literal

from modules.eis.eis_enums import EisTransClass
from modules.eis.eis_schema import EisCasInvoice, EisLineItem

# Tax classification categories per BIR EIS guidelines Section 5
TaxClassification = Literal["VATABLE", "ZERO_RATED", "EXEMPT"]

_TAX_CLASS_CODE_MAP = {
    "VATABLE": EisTransClass.VATABLE.value,       # "01"
    "ZERO_RATED": EisTransClass.ZERO_RATED.value, # "02"
    "EXEMPT": EisTransClass.EXEMPT.value,         # "03"
}


def _classify_line_item(item: EisLineItem) -> TaxClassification:
    """Classify an individual line item's tax treatment.

    EXTENSION POINT:
    When the CAS tax data model is finalized with the accounting team,
    update only this function to inspect line item attributes (e.g. item.tax_type
    or item.Desc) or join with the CAS products/services catalog.

    Default stub behavior: Returns "VATABLE" for all items.
    Since all items in a stub batch will belong to the "VATABLE" group,
    no splitting occurs unless this function returns differing values.
    """
    # TODO: Replace with dynamic field lookup when CAS product tax model is connected
    return "VATABLE"


def check_mixed_tax_split(invoice: EisCasInvoice) -> List[EisCasInvoice]:
    """Inspect invoice line items and split if mixed tax treatments are detected.

    BIR EIS API Development Guide Section 5 (Pages 18-24):
    Invoices containing mixed VATable, zero-rated, and exempt items must be
    segregated into separate document submissions to ensure correct tax ledgering.
    Per Section 5.2:
    - Separately sent invoices have the same Invoice Number (CompInvoiceId) in EIS.
    - Each separate invoice has its own 24-character EisUniqueId.
    - Each separate invoice is stamped with its respective TransClass (01, 02, 03).

    Returns:
    - [invoice] if all line items share the same tax classification.
    - [inv_1, inv_2, ...] if multiple classifications exist, with recalculated totals,
      recalculated VAT, identical CompInvoiceId, and valid 24-character EisUniqueIds.
    """
    if not invoice.ItemList:
        return [invoice]

    # Group line items by tax category
    groups: Dict[TaxClassification, List[EisLineItem]] = {}
    for item in invoice.ItemList:
        cls = _classify_line_item(item)
        groups.setdefault(cls, []).append(item)

    # If only one tax group exists, assign correct TransClass and return single invoice
    if len(groups) <= 1:
        tax_class = next(iter(groups.keys()))
        expected_trans_class = _TAX_CLASS_CODE_MAP.get(tax_class, EisTransClass.VATABLE.value)
        if invoice.TransClass != expected_trans_class:
            return [invoice.model_copy(update={"TransClass": expected_trans_class})]
        return [invoice]

    split_invoices: List[EisCasInvoice] = []
    prefix_16 = invoice.EisUniqueId[:16]
    seq_suffix = invoice.EisUniqueId[16:] if len(invoice.EisUniqueId) >= 24 else "00000000"

    for idx, (tax_class, items) in enumerate(groups.items()):
        # Sum line item net sales for this group
        group_net_sales = sum(item.NetSales for item in items)

        # Pro-rate discount if applicable or retain proportional discount
        total_orig_sales = invoice.TotNetItemSales or Decimal("1.0")
        ratio = group_net_sales / total_orig_sales if total_orig_sales > 0 else Decimal("1.0")
        group_sales_after_discount = (invoice.TotNetSalesAftDisct * ratio).quantize(Decimal("0.01"))

        # Calculate VAT based on category (12% for VATable, 0.00 for Zero-Rated & Exempt)
        if tax_class == "VATABLE":
            group_vat = (group_sales_after_discount * Decimal("0.12")).quantize(Decimal("0.01"))
        else:
            group_vat = Decimal("0.00")

        group_net_payable = (group_sales_after_discount + group_vat).quantize(Decimal("0.01"))

        # Construct strictly 24-character alphanumeric Unique ID (no hyphens)
        if seq_suffix.isdigit():
            base_num = int(seq_suffix)
            new_seq = f"{(base_num + idx):08d}"[-8:]
        else:
            new_seq = f"{seq_suffix[:7]}{idx + 1}"[:8]
        new_unique_id = f"{prefix_16}{new_seq}"

        trans_class_code = _TAX_CLASS_CODE_MAP.get(tax_class, EisTransClass.VATABLE.value)

        # Cloned invoice: CompInvoiceId remains identical per BIR Section 5.2
        cloned_invoice = invoice.model_copy(
            update={
                "EisUniqueId": new_unique_id,
                "CompInvoiceId": invoice.CompInvoiceId,
                "TransClass": trans_class_code,
                "ItemList": items,
                "TotNetItemSales": group_net_sales,
                "TotNetSalesAftDisct": group_sales_after_discount,
                "VATAmt": group_vat,
                "NetAmtPay": group_net_payable,
            }
        )
        split_invoices.append(cloned_invoice)

    return split_invoices
