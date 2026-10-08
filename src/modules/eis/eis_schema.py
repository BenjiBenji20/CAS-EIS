from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from base.schema import BaseSchema
from core.settings import settings
from modules.eis.eis_enums import (
    EisCorrectionCode,
    EisDocType,
    EisFailReason,
    EisProcessStatus,
    EisResultStatus,
    EisTransClass,
    EisTransmissionStatus,
)
from utils.schema_response import SchemaResponseDetails


# ─────────────────────────────────────────────────────────────────────────────
# 1. BIR CAS INVOICE SCHEMAS (PascalCase, strict extra="forbid", Decimal types)
# ─────────────────────────────────────────────────────────────────────────────

class EisBirBaseModel(BaseModel):
    """Base class for BIR payload schemas to enforce strict PascalCase and no unknown fields."""
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        from_attributes=True,
    )


class EisSellerInfo(EisBirBaseModel):
    """Seller registered tax info (BIR Guide Section 4.1, Page 12; CAS Format Excel Row 22)."""
    Tin: str = Field(..., max_length=9, description="Seller registered TIN without branch code")
    BranchCd: str = Field(..., max_length=5, description="5-digit zero-padded branch code")
    Type: str = Field(..., max_length=1, description="0: VAT registered, 1: Non-VAT registered")
    RegNm: str = Field(..., max_length=200, description="Registered Name")
    BusinessNm: str = Field(..., max_length=200, description="Trade/Business Name")
    Email: Optional[str] = Field(None, max_length=100, description="Seller email address")
    RegAddr: str = Field(..., max_length=300, description="Registered Address")

    @field_validator("BranchCd", mode="before")
    @classmethod
    def pad_branch_code(cls, v: str) -> str:
        if v is not None:
            return str(v).strip().zfill(5)[:5]
        return v

    @field_validator("Type")
    @classmethod
    def validate_seller_type(cls, v: str) -> str:
        val = str(v).strip()
        if val not in ("0", "1"):
            raise ValueError(
                f"SellerInfo.Type must be '0' (VAT registered) or '1' (Non-VAT registered), received: '{v}'"
            )
        return val


class EisBuyerInfo(EisBirBaseModel):
    """Buyer tax info & proof of delivery (BIR Guide Section 4.1, Pages 13-14; CAS Format Excel Row 28-38)."""
    Tin: str = Field(..., max_length=9, description="Buyer TIN (use '000000000' if unregistered)")
    BranchCd: str = Field(default="00000", max_length=5, description="5-digit zero-padded branch code")
    RegNm: str = Field(..., max_length=200, description="Buyer Registered Name")
    BusinessNm: str = Field(..., max_length=200, description="Buyer Trade/Business Name")
    Email: Optional[str] = Field(None, max_length=100, description="Buyer email address")
    RegAddr: Optional[str] = Field(None, max_length=300, description="Buyer Registered Address")

    # Proof of Delivery / Export fields (combined into BuyerInfo per BIR spec)
    DevAddr: Optional[str] = Field(None, max_length=300, description="Delivery Address")
    AirNum: Optional[str] = Field(None, max_length=50, description="Airway Bill Number")
    AirNumDt: Optional[str] = Field(None, max_length=8, description="Airway Bill Date YYYYMMDD")
    LadNum: Optional[str] = Field(None, max_length=50, description="Bill of Lading Number")
    LadNumDt: Optional[str] = Field(None, max_length=8, description="Bill of Lading Date YYYYMMDD")

    @field_validator("BranchCd", mode="before")
    @classmethod
    def pad_branch_code(cls, v: Optional[str]) -> str:
        if v is not None:
            val_str = str(v).strip()
            if len(val_str) > 0 and len(val_str) < 5 and val_str.isdigit():
                return val_str.zfill(5)
            return val_str[:5]
        return "00000"


class EisLineItem(EisBirBaseModel):
    """Line item specification (BIR Guide Section 4.1, Pages 14-16)."""
    Nm: str = Field(..., max_length=100, description="Item Name")
    Desc: Optional[str] = Field(None, max_length=100, description="Item Description or Service details")
    Qty: Decimal = Field(default=Decimal("0.0"), description="Quantity")
    Unit: Optional[str] = Field(None, max_length=50, description="Unit of measure (e.g. PCS, KGS, HRS)")
    UnitCost: Decimal = Field(default=Decimal("0.0"), description="Unit cost")
    SalesAmt: Decimal = Field(default=Decimal("0.0"), description="Gross Sales Amount")
    RegDscntAmt: Decimal = Field(default=Decimal("0.0"), description="Regular Discount Amount")
    SpeDscntAmt: Decimal = Field(default=Decimal("0.0"), description="Special Discount Amount")
    NetSales: Decimal = Field(default=Decimal("0.0"), description="Net of Item Sales")


class EisDiscountInfo(EisBirBaseModel):
    """Summary discount breakdown (BIR Guide Section 4.1, Pages 16-17)."""
    ScAmt: Decimal = Field(default=Decimal("0.0"), description="Senior Citizen Discount Amount")
    PwdAmt: Decimal = Field(default=Decimal("0.0"), description="PWD Discount Amount")
    RegAmt: Decimal = Field(default=Decimal("0.0"), description="Regular Discount Amount")
    SpeAmt: Decimal = Field(default=Decimal("0.0"), description="Special Discount Amount")
    Rmk2: Optional[str] = Field(None, description="Remarks 2")


class EisForeignCurrency(EisBirBaseModel):
    """Foreign currency specification for export/forex invoices (BIR Guide Section 4.1, Page 22)."""
    Currency: str = Field(..., max_length=3, description="ISO Currency Code (e.g. USD, JPY)")
    ConvRate: Decimal = Field(..., description="Conversion rate to PHP")
    ForexAmt: Decimal = Field(..., description="Amount in foreign currency")


class EisCasInvoice(EisBirBaseModel):
    """Complete CAS Issued Invoice schema (BIR EIS API Guide Section 4.1, Pages 10-23)."""
    # Management Information
    CompInvoiceId: str = Field(..., max_length=50, description="Company internal invoice/receipt number")
    IssueDtm: str = Field(..., max_length=8, description="Issuance date in YYYYMMDD format")

    # BIR e-Invoice Basic Information
    EisUniqueId: str = Field(
        ...,
        min_length=24,
        max_length=24,
        description="BIR Unique ID: 24 alphanumeric digits (YYYYMMDD [8] + Accreditation ID [8] + Control/Sequence [8])"
    )
    DocType: str = Field(..., max_length=2, description="Document type (01=SI, 02=DM, 03=CM, 04=SB, 05=OR)")
    TransClass: str = Field(..., max_length=2, description="Tax classification (01=VATable, 02=Zero-Rated, 03=Exempt)")

    # Invoice Correction fields
    CorrYN: Literal["Y", "N"] = Field(..., max_length=1, description="Correction flag: 'Y' or 'N'")
    CorrectionCd: Optional[str] = Field(None, max_length=2, description="Correction code (01=Cancel, 02=Modify)")
    PrevUniqueId: Optional[str] = Field(None, max_length=24, description="EisUniqueId of document being corrected")
    Rmk1: Optional[str] = Field(None, max_length=500, description="Remarks 1")

    # Seller & Buyer Info
    SellerInfo: EisSellerInfo = Field(..., description="Seller tax information")
    BuyerInfo: EisBuyerInfo = Field(..., description="Buyer tax information")

    # Line Items
    ItemList: List[EisLineItem] = Field(..., min_length=1, max_length=1000, description="Line item details")
    TotNetItemSales: Decimal = Field(..., description="Total of Net Item Sales")

    # Sales & Discount Summary
    Discount: EisDiscountInfo = Field(..., description="Discount breakdown")
    OtherTaxRev: Decimal = Field(default=Decimal("0.0"), description="Other taxable revenue")
    TotNetSalesAftDisct: Decimal = Field(..., description="Total Net Sales after discounts")

    # Tax Information
    VATAmt: Decimal = Field(..., description="VAT Amount (12% of VATable sales)")
    WithholdIncome: Decimal = Field(default=Decimal("0.0"), description="Withholding Tax - Income Tax")
    WithholdBusVAT: Decimal = Field(default=Decimal("0.0"), description="Withholding Tax - Business VAT")
    WithholdBusPT: Decimal = Field(default=Decimal("0.0"), description="Withholding Tax - Business Percentage")

    # Non-taxable & Net Payable
    OtherNonTaxCharge: Decimal = Field(default=Decimal("0.0"), description="Other Non-taxable charges")
    NetAmtPay: Decimal = Field(..., description="Net Amount Payable")

    # Optional Foreign Currency & PTU
    ForCur: Optional[EisForeignCurrency] = Field(None, description="Foreign currency info")
    PtuNum: str = Field(
        default_factory=lambda: settings.EIS_PTU_NUM or "",
        max_length=50,
        description="BIR Permit To Use (PTU) or Acknowledgment Certificate Control Number"
    )

    @field_validator("DocType", mode="before")
    @classmethod
    def format_doc_type(cls, v: str) -> str:
        if isinstance(v, EisDocType):
            return v.value
        return str(v).strip().zfill(2)[:2]

    @field_validator("TransClass", mode="before")
    @classmethod
    def format_trans_class(cls, v: str) -> str:
        if isinstance(v, EisTransClass):
            return v.value
        return str(v).strip().zfill(2)[:2]

    @field_validator("CorrectionCd", mode="before")
    @classmethod
    def format_correction_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, EisCorrectionCode):
            return v.value
        return str(v).strip().zfill(2)[:2]

    @field_validator("IssueDtm")
    @classmethod
    def validate_issue_date(cls, v: str) -> str:
        val_str = v.strip()
        if len(val_str) != 8 or not val_str.isdigit():
            raise ValueError(f"IssueDtm must be 8 digits in YYYYMMDD format, received: {v}")
        return val_str

    @field_validator("EisUniqueId")
    @classmethod
    def validate_eis_unique_id(cls, v: str) -> str:
        val_str = v.strip()
        if len(val_str) != 24 or not val_str.isalnum():
            raise ValueError(
                f"EisUniqueId must be exactly 24 alphanumeric characters without hyphens, received: '{v}'"
            )
        return val_str

    @field_validator("PtuNum", mode="before")
    @classmethod
    def default_ptu_num(cls, v: Optional[str]) -> str:
        val = str(v).strip() if v else (settings.EIS_PTU_NUM or "").strip()
        if not val:
            return "UNREGISTERED-PTU"
        return val[:50]

    @model_validator(mode="after")
    def validate_bir_corrections(self) -> "EisCasInvoice":
        if self.CorrYN == "Y":
            if not self.CorrectionCd or self.CorrectionCd not in ("01", "02"):
                raise ValueError("CorrectionCd ('01'=Cancel, '02'=Modify) is mandatory when CorrYN is 'Y'")
            if not self.PrevUniqueId or len(self.PrevUniqueId) != 24:
                raise ValueError("PrevUniqueId must be exactly 24 characters when CorrYN is 'Y'")
        else:
            if self.CorrectionCd:
                self.CorrectionCd = ""
            if self.PrevUniqueId:
                self.PrevUniqueId = ""
        return self


# ─────────────────────────────────────────────────────────────────────────────
# 2. INTERNAL API SCHEMAS (Inherits BaseSchema for camelCase serialization)
# ─────────────────────────────────────────────────────────────────────────────

class EisTransmitRequest(BaseSchema):
    """Payload for internal transmission trigger."""
    invoices: List[EisCasInvoice] = Field(..., min_length=1, description="List of CAS invoices to transmit")


class EisTransmissionItemResponse(BaseSchema):
    """Per-invoice result status from BIR EIS audit log."""
    id: UUID
    eis_unique_id: str
    comp_invoice_id: Optional[str] = None
    result_status: EisResultStatus
    fail_reason_code: Optional[str] = None
    fail_message: Optional[str] = None
    created_at: datetime


class EisTransmitResponse(BaseSchema):
    """Response returned upon transmitting a batch to BIR EIS."""
    id: UUID
    submit_id: str
    status: EisTransmissionStatus
    ack_id: Optional[str] = None
    invoice_count: int
    submitted_at: Optional[datetime] = None
    response_details: SchemaResponseDetails


class EisInquiryResponse(BaseSchema):
    """Audit inquiry response detailing batch status and per-invoice results."""
    id: UUID
    submit_id: str
    status: EisTransmissionStatus
    ack_id: Optional[str] = None
    invoice_count: int
    process_status_code: Optional[str] = None
    submitted_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    items: List[EisTransmissionItemResponse] = Field(default_factory=list)
    response_details: SchemaResponseDetails
