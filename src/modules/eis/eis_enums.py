from enum import Enum


class EisDocType(str, Enum):
    """Document Type Classification for CAS (BIR CAS JSON File Format v2.01 Row 12)."""
    SI = "01"  # Sales Invoice
    DM = "02"  # Debit Memo / Debit Note (DN)
    CM = "03"  # Credit Memo / Credit Note (CN)
    SB = "04"  # Service Billing (Statement of Account / Billing Statement)
    OR = "05"  # Official Receipt


class EisTransClass(str, Enum):
    """Transaction Tax Classification for CAS (BIR CAS JSON File Format v2.01 Row 13).

    For mixed transaction data in a single document, invoices must be transmitted
    individually per tax classification:
    01 : VATable
    02 : Zero-Rated
    03 : VAT Exempt
    """
    VATABLE = "01"     # VATable Sales
    ZERO_RATED = "02"  # Zero-Rated Sales
    EXEMPT = "03"      # VAT Exempt Sales


class EisCorrectionCode(str, Enum):
    """e-Invoice Correction Code (BIR EIS API Guide Section 4.1, Page 11)."""
    CANCEL = "01"  # Cancellation
    MODIFY = "02"  # Modification


class EisProcessStatus(str, Enum):
    """Inquiry Process Status Code (BIR EIS API Guide Section 7.3.3.7.1, Page 44)."""
    COMPLETED = "01"          # Batch processing completed
    PROCESSING = "02"         # Batch in processing (verification in progress)
    UNABLE_TO_PROCESS = "03"  # Unable to process (e.g. decryption error)


class EisResultStatus(str, Enum):
    """Transmission Item Result Status Category."""
    SUCCESS = "SUC"       # Document validated and stored (e.g. SUC001)
    SYNTAX_ERROR = "SYN"  # Payload syntax or format validation error (e.g. SYN002-SYN004)
    RULE_ERROR = "ERR"    # Business rule validation error (e.g. ERR001-ERR007, ERR999)

    @classmethod
    def from_bir_code(cls, code: str) -> "EisResultStatus":
        """Safely map 6-character BIR result status code to EisResultStatus enum."""
        if not code:
            return cls.RULE_ERROR
        upper_code = str(code).strip().upper()
        if upper_code.startswith("SUC"):
            return cls.SUCCESS
        if upper_code.startswith("SYN"):
            return cls.SYNTAX_ERROR
        return cls.RULE_ERROR


class EisTransmissionStatus(str, Enum):
    """Internal transmission lifecycle status for audit and retry handling."""
    PENDING = "PENDING"            # Prepared, awaiting sending
    SENT = "SENT"                  # Sent to BIR, received ackId, awaiting polling
    ACKNOWLEDGED = "ACKNOWLEDGED"  # Polled and confirmed processed by BIR
    FAILED = "FAILED"              # Transmission rejected or unrecoverable error
    PARTIAL = "PARTIAL"            # Completed with mixed SUC and ERR/SYN items


class EisFailReason(str, Enum):
    """Official BIR EIS Processing Result Codes (BIR EIS API Guide Section 7.3.3.7.2 & 7.3.3.7.3, Pages 44-45)."""
    # Success Code
    SUC001 = "SUC001"  # Success - Passed all verification processes

    # Syntax Validation Result Codes
    SYN002 = "SYN002"  # Invalid signature - Digital signature is not valid
    SYN003 = "SYN003"  # Duplicated EisUniqueId - Already registered in BIR
    SYN004 = "SYN004"  # e-Invoice schema error - Structure, required fields, data type, number formats

    # Business Rule Validation Result Codes
    ERR001 = "ERR001"  # Seller TIN error - Seller TIN is not registered in BIR
    ERR002 = "ERR002"  # Issuance datetime error - Invalid, after transmission, or mismatched in EisUniqueId
    ERR003 = "ERR003"  # Transmission datetime error - Invalid transmission date
    ERR004 = "ERR004"  # Total Sales Amount / VAT Amount error - Sign mismatch or non-zero VAT for zero-rated/exempt
    ERR006 = "ERR006"  # Accreditation ID error - Accreditation ID in EisUniqueId does not match system
    ERR007 = "ERR007"  # E-invoice Unique ID to be corrected error - Invalid or non-existent PrevUniqueId
    ERR999 = "ERR999"  # Other undefined error

    # Fail Reason Status Codes (when processStatusCode is '03')
    FRS001 = "FRS001"  # Non-existent submitId
    FRS002 = "FRS002"  # Decryption failure - AES-256 encrypted payload cannot be decrypted
