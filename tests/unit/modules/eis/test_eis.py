import base64
from decimal import Decimal
import json
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives import hashes, serialization

from modules.eis.eis_enums import (
    EisCorrectionCode,
    EisDocType,
    EisProcessStatus,
    EisResultStatus,
    EisTransClass,
    EisTransmissionStatus,
)
from modules.eis.eis_schema import (
    EisBuyerInfo,
    EisCasInvoice,
    EisDiscountInfo,
    EisLineItem,
    EisSellerInfo,
)
from modules.eis import eis_crypto
from modules.eis.eis_splitter import check_mixed_tax_split, _classify_line_item


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database():
    """Override conftest database setup fixture for standalone EIS unit tests."""
    yield


@pytest.fixture
def rsa_key_pair():
    """Generate RSA 2048-bit test key pair."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pub_pem, priv_pem


@pytest.fixture
def sample_invoice():
    """Create a valid sample CAS invoice."""
    return EisCasInvoice(
        CompInvoiceId="INV-2026-0001",
        IssueDtm="20261003",
        EisUniqueId="2026100320146IT400000001",
        DocType="01",
        TransClass="01",
        CorrYN="N",
        SellerInfo=EisSellerInfo(
            Tin="123456789",
            BranchCd="1",
            Type="0",
            RegNm="Acme Corporation",
            BusinessNm="Acme Trading",
            RegAddr="123 Ayala Ave, Makati City",
        ),
        BuyerInfo=EisBuyerInfo(
            Tin="987654321",
            BranchCd="0",
            RegNm="Client Inc",
            BusinessNm="Client Services",
        ),
        ItemList=[
            EisLineItem(
                Nm="Software License",
                Qty=Decimal("2"),
                Unit="PCS",
                UnitCost=Decimal("500.00"),
                SalesAmt=Decimal("1000.00"),
                RegDscntAmt=Decimal("0.00"),
                SpeDscntAmt=Decimal("0.00"),
                NetSales=Decimal("1000.00"),
            )
        ],
        TotNetItemSales=Decimal("1000.00"),
        Discount=EisDiscountInfo(),
        TotNetSalesAftDisct=Decimal("1000.00"),
        VATAmt=Decimal("120.00"),
        WithholdIncome=Decimal("0.00"),
        WithholdBusVAT=Decimal("0.00"),
        WithholdBusPT=Decimal("0.00"),
        OtherNonTaxCharge=Decimal("0.00"),
        NetAmtPay=Decimal("1120.00"),
    )


class TestEisCrypto:
    def test_auth_key_generation(self):
        k1 = eis_crypto.generate_auth_key()
        k2 = eis_crypto.generate_auth_key()
        assert len(k1) == 32
        assert len(k2) == 32
        assert k1 != k2

    def test_format_datetime(self):
        dt_str = eis_crypto.format_datetime()
        assert len(dt_str) == 14
        assert dt_str.isdigit()

    def test_aes_encrypt_decrypt_roundtrip(self):
        key = eis_crypto.generate_auth_key()
        text = "Confidential BIR Invoice Transmission Payload"
        encrypted = eis_crypto.aes_encrypt(text, key)
        assert encrypted != text
        decrypted = eis_crypto.aes_decrypt(encrypted, key)
        assert decrypted == text

    def test_hmac_sign_base64_output(self):
        sig = eis_crypto.hmac_sign("20261003120000POST/api/v2/authentication", "secret-key")
        assert len(sig) > 0
        decoded = base64.b64decode(sig)
        assert len(decoded) == 32  # SHA-256 digest is 32 bytes

    def test_rsa_encrypt_pkcs1v15(self, rsa_key_pair):
        pub_pem, priv_pem = rsa_key_pair
        payload = '{"userId":"test","password":"secret","authKey":"123"}'
        encrypted_b64 = eis_crypto.rsa_encrypt(payload, pub_pem)

        cipher_bytes = base64.b64decode(encrypted_b64)
        priv_key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
        decrypted = priv_key.decrypt(cipher_bytes, asym_padding.PKCS1v15()).decode("utf-8")
        assert decrypted == payload

    def test_jws_rs256_sign_and_verify(self, rsa_key_pair):
        pub_pem, priv_pem = rsa_key_pair
        payload = '{"CompInvoiceId":"INV-999"}'
        key_id = "test-key-id-001"

        token = eis_crypto.jws_sign(payload, priv_pem, key_id)
        parts = token.split(".")
        assert len(parts) == 3

        # Header check
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode())
        assert header["alg"] == "RS256"
        assert header["kid"] == key_id

        # Payload check
        raw_payload = base64.urlsafe_b64decode(parts[1] + "==").decode()
        assert raw_payload == payload

        # Verify signature with public key
        pub_key = serialization.load_pem_public_key(pub_pem.encode())
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        sig_bytes = base64.urlsafe_b64decode(parts[2] + "==")
        pub_key.verify(sig_bytes, signing_input, asym_padding.PKCS1v15(), hashes.SHA256())


class TestEisSchema:
    def test_padding_and_validation(self, sample_invoice):
        # Branch code padded to 5 chars
        assert sample_invoice.SellerInfo.BranchCd == "00001"
        assert sample_invoice.BuyerInfo.BranchCd == "00000"
        # DocType padded to 2 chars
        assert sample_invoice.DocType == "01"
        assert sample_invoice.TransClass == "01"

    def test_invalid_issue_dtm(self, sample_invoice):
        data = sample_invoice.model_dump()
        data["IssueDtm"] = "2026-10-03"  # Hyphenated format should fail
        with pytest.raises(ValueError):
            EisCasInvoice.model_validate(data)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValueError):
            EisLineItem(
                Nm="Item 1",
                Qty=Decimal("1"),
                UnitCost=Decimal("100"),
                SalesAmt=Decimal("100"),
                NetSales=Decimal("100"),
                # pyrefly: ignore [unexpected-keyword]
                UnknownField="illegal",  # Should be rejected
            )


class TestEisSplitter:
    def test_unmixed_invoice_remains_single(self, sample_invoice):
        split = check_mixed_tax_split(sample_invoice)
        assert len(split) == 1
        assert split[0].EisUniqueId == sample_invoice.EisUniqueId

    def test_mixed_invoice_splitting(self, sample_invoice, monkeypatch):
        # Create an invoice with two items
        inv = sample_invoice.model_copy(
            update={
                "ItemList": [
                    EisLineItem(
                        Nm="Item A",
                        Qty=Decimal("1"),
                        UnitCost=Decimal("100.00"),
                        SalesAmt=Decimal("100.00"),
                        NetSales=Decimal("100.00"),
                    ),
                    EisLineItem(
                        Nm="Item B",
                        Qty=Decimal("1"),
                        UnitCost=Decimal("200.00"),
                        SalesAmt=Decimal("200.00"),
                        NetSales=Decimal("200.00"),
                    ),
                ],
                "TotNetItemSales": Decimal("300.00"),
                "TotNetSalesAftDisct": Decimal("300.00"),
                "VATAmt": Decimal("12.00"),
                "NetAmtPay": Decimal("312.00"),
            }
        )

        # Mock _classify_line_item so Item A is VATABLE and Item B is ZERO_RATED
        def mock_classify(item):
            return "VATABLE" if item.Nm == "Item A" else "ZERO_RATED"

        monkeypatch.setattr("modules.eis.eis_splitter._classify_line_item", mock_classify)

        split_list = check_mixed_tax_split(inv)
        assert len(split_list) == 2
        # Check CompInvoiceId remains identical per BIR Section 5.2
        assert split_list[0].CompInvoiceId == "INV-2026-0001"
        assert split_list[1].CompInvoiceId == "INV-2026-0001"
        # Check 24-char EisUniqueId format
        assert len(split_list[0].EisUniqueId) == 24
        assert len(split_list[1].EisUniqueId) == 24
        assert split_list[0].EisUniqueId != split_list[1].EisUniqueId
        # Check TransClass assignment
        assert split_list[0].TransClass == "01"  # VATable
        assert split_list[1].TransClass == "02"  # Zero-Rated
        # Item A: VATABLE
        assert split_list[0].VATAmt == Decimal("12.00")
        assert split_list[0].NetAmtPay == Decimal("112.00")
        # Item B: ZERO_RATED (0% VAT)
        assert split_list[1].VATAmt == Decimal("0.00")
        assert split_list[1].NetAmtPay == Decimal("200.00")

    def test_doc_type_and_trans_class_enums(self):
        # BIR CAS v2.01 doc types
        assert EisDocType.SI.value == "01"
        assert EisDocType.DM.value == "02"
        assert EisDocType.CM.value == "03"
        assert EisDocType.SB.value == "04"
        assert EisDocType.OR.value == "05"

        # BIR CAS v2.01 tax classes
        assert EisTransClass.VATABLE.value == "01"
        assert EisTransClass.ZERO_RATED.value == "02"
        assert EisTransClass.EXEMPT.value == "03"

    def test_eis_result_status_from_bir_code(self):
        assert EisResultStatus.from_bir_code("SUC001") == EisResultStatus.SUCCESS
        assert EisResultStatus.from_bir_code("SYN004") == EisResultStatus.SYNTAX_ERROR
        assert EisResultStatus.from_bir_code("ERR001") == EisResultStatus.RULE_ERROR
        assert EisResultStatus.from_bir_code("unknown") == EisResultStatus.RULE_ERROR

    def test_invoice_correction_validation(self, sample_invoice):
        # Valid correction
        valid_data = {
            **sample_invoice.model_dump(),
            "CorrYN": "Y",
            "CorrectionCd": "01",
            "PrevUniqueId": "2026100120146IT400000001",
        }
        corr_inv = EisCasInvoice.model_validate(valid_data)
        assert corr_inv.CorrYN == "Y"
        assert corr_inv.CorrectionCd == "01"
        assert corr_inv.PrevUniqueId == "2026100120146IT400000001"

        # Missing CorrectionCd when CorrYN == 'Y' should fail
        with pytest.raises(ValueError):
            invalid_data = {
                **sample_invoice.model_dump(),
                "CorrYN": "Y",
                "CorrectionCd": None,
                "PrevUniqueId": "2026100120146IT400000001",
            }
            EisCasInvoice.model_validate(invalid_data)

        # Invalid PrevUniqueId length when CorrYN == 'Y' should fail
        with pytest.raises(ValueError):
            invalid_data2 = {
                **sample_invoice.model_dump(),
                "CorrYN": "Y",
                "CorrectionCd": "01",
                "PrevUniqueId": "SHORT-ID",
            }
            EisCasInvoice.model_validate(invalid_data2)
