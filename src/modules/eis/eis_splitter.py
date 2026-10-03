from decimal import Decimal
from typing import Dict, List, Literal

from modules.eis.eis_schema import EisCasInvoice, EisLineItem

# Tax classification categories per BIR EIS guidelines Section 5
TaxClassification = Literal["VATABLE", "ZERO_RATED", "EXEMPT"]


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

    BIR EIS API Development Guide Section 5 (Page 9):
    Invoices containing mixed VATable, zero-rated, and exempt items must be
    segregated into separate document submissions to ensure correct tax ledgering.

    Returns:
    - [invoice] if all line items share the same tax classification.
    - [inv_1, inv_2, ...] if multiple classifications exist, with recalculated totals
      and suffixed EisUniqueIds.
    """
    if not invoice.ItemList:
        return [invoice]

    # Group line items by tax category
    groups: Dict[TaxClassification, List[EisLineItem]] = {}
    for item in invoice.ItemList:
        cls = _classify_line_item(item)
        groups.setdefault(cls, []).append(item)

    # If only one tax group exists, no splitting required
    if len(groups) <= 1:
        return [invoice]

    split_invoices: List[EisCasInvoice] = []
    suffix_index = 0
    suffixes = ["A", "B", "C", "D", "E"]

    for tax_class, items in groups.items():
        suffix = suffixes[suffix_index] if suffix_index < len(suffixes) else str(suffix_index + 1)
        suffix_index += 1

        # Sum line item net sales
        group_net_sales = sum(item.NetSales for item in items)

        # Pro-rate discount if applicable or retain proportional discount
        total_orig_sales = invoice.TotNetItemSales or Decimal("1.0")
        ratio = group_net_sales / total_orig_sales if total_orig_sales > 0 else Decimal("1.0")
        group_sales_after_discount = (invoice.TotNetSalesAftDisct * ratio).quantize(Decimal("0.01"))

        # Calculate VAT based on category
        if tax_class == "VATABLE":
            group_vat = (group_sales_after_discount * Decimal("0.12")).quantize(Decimal("0.01"))
        else:
            group_vat = Decimal("0.00")

        group_net_payable = (group_sales_after_discount + group_vat).quantize(Decimal("0.01"))

        # Construct suffixed Unique ID (max 24 characters)
        base_unique_id = invoice.EisUniqueId
        if len(base_unique_id) > 22:
            base_unique_id = base_unique_id[:22]
        new_unique_id = f"{base_unique_id}-{suffix}"

        # Create cloned invoice for this tax bucket
        cloned_invoice = invoice.model_copy(
            update={
                "EisUniqueId": new_unique_id,
                "CompInvoiceId": f"{invoice.CompInvoiceId}-{suffix}",
                "ItemList": items,
                "TotNetItemSales": group_net_sales,
                "TotNetSalesAftDisct": group_sales_after_discount,
                "VATAmt": group_vat,
                "NetAmtPay": group_net_payable,
            }
        )
        split_invoices.append(cloned_invoice)

    return split_invoices
