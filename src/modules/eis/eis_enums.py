from enum import Enum


class EisDocType(str, Enum):
    """Document Type Classification (BIR EIS API Guide Section 4.1, Page 10)."""
    SI = "01"  # Sales Invoice
    OR = "02"  # Official Receipt
    SB = "03"  # Special / Billing Invoice
    DM = "04"  # Debit Memo
    CM = "05"  # Credit Memo


class EisTransClass(str, Enum):
    """Transaction Classification (BIR EIS API Guide Section 4.1, Page 10)."""
    B2B = "01"     # Business to Business
    B2C = "02"     # Business to Consumer
    B2G = "03"     # Business to Government
    EXPORT = "04"  # Export


class EisCorrectionCode(str, Enum):
    """e-Invoice Correction Code (BIR EIS API Guide Section 4.1, Page 11)."""
    CANCEL = "01"  # Cancellation
    MODIFY = "02"  # Modification


class EisProcessStatus(str, Enum):
    """Inquiry Process Status Code (BIR EIS API Guide Section 7.3.1, Page 42)."""
    PROCESSING = "00"  # Batch still being processed by BIR EIS
    COMPLETED = "01"   # Batch processing completed


class EisResultStatus(str, Enum):
    """Transmission Item Result Status (BIR EIS API Guide Section 7.3.1, Page 42)."""
    SUCCESS = "SUC"       # Document validated and stored
    SYNTAX_ERROR = "SYN"  # Payload syntax or format validation error
    RULE_ERROR = "ERR"    # Business rule validation error


class EisTransmissionStatus(str, Enum):
    """Internal transmission lifecycle status for audit and retry handling."""
    PENDING = "PENDING"            # Prepared, awaiting sending
    SENT = "SENT"                  # Sent to BIR, received ackId, awaiting polling
    ACKNOWLEDGED = "ACKNOWLEDGED"  # Polled and confirmed processed by BIR
    FAILED = "FAILED"              # Transmission rejected or unrecoverable error
    PARTIAL = "PARTIAL"            # Completed with mixed SUC and ERR/SYN items


class EisFailReason(str, Enum):
    """BIR EIS Failure Reason Codes (BIR EIS API Guide Section 7.3.1, Pages 43-44)."""
    # Syntax Validation Codes
    SYN001 = "SYN001"  # Mandatory Field Missing
    SYN002 = "SYN002"  # Data Type Mismatch
    SYN003 = "SYN003"  # Field Length Exceeded
    SYN004 = "SYN004"  # Invalid Format
    SYN005 = "SYN005"  # Invalid Code Value
    SYN006 = "SYN006"  # Invalid Decimal Places
    SYN007 = "SYN007"  # Duplicate Invoice Number
    SYN008 = "SYN008"  # JWS Verification Failed
    SYN009 = "SYN009"  # Decryption Failed
    SYN010 = "SYN010"  # Invalid Date Range
    SYN011 = "SYN011"  # Invalid Array Length
    SYN012 = "SYN012"  # Unauthorized Seller TIN
    SYN013 = "SYN013"  # Invalid PTU Number
    SYN014 = "SYN014"  # Expired Certificate
    SYN015 = "SYN015"  # General Syntax Error

    # Business Rule Validation Codes
    ERR001 = "ERR001"  # Total Amount Calculation Mismatch
    ERR002 = "ERR002"  # VAT Calculation Mismatch
    ERR003 = "ERR003"  # Net Sales Calculation Mismatch
    ERR004 = "ERR004"  # Discount Calculation Mismatch
    ERR005 = "ERR005"  # Withholding Tax Calculation Mismatch
    ERR006 = "ERR006"  # Line Item Total Mismatch
    ERR007 = "ERR007"  # Referenced Document Not Found (Correction)
    ERR008 = "ERR008"  # Document Already Cancelled
    ERR009 = "ERR009"  # Seller TIN Not Registered in EIS
    ERR010 = "ERR010"  # General Business Rule Error
