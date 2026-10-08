import asyncio
from datetime import datetime, timezone
import json
import secrets
from typing import List, Optional, Tuple
import uuid

from fastapi import Depends
import httpx
from loguru import logger

from core.settings import settings
from exceptions.app_exception import (
    BadRequestException,
    InternalServerException,
    NotFoundException,
)
from modules.eis.eis_crypto import (
    aes_decrypt,
    aes_encrypt,
    format_datetime,
    generate_auth_key,
    hmac_sign,
    jws_sign,
    rsa_encrypt,
)
from modules.eis.eis_enums import (
    EisProcessStatus,
    EisResultStatus,
    EisTransmissionStatus,
)
from modules.eis.eis_model import EisSession, EisTransmission
from modules.eis.eis_repository import (
    EisSessionRepository,
    EisTransmissionItemRepository,
    EisTransmissionRepository,
)
from modules.eis.eis_schema import (
    EisCasInvoice,
    EisInquiryResponse,
    EisTransmissionItemResponse,
    EisTransmitResponse,
)
from modules.eis.eis_splitter import check_mixed_tax_split
from utils.schema_response import SchemaResponseDetails


class EisService:
    """Orchestrates BIR EIS authentication, document signing, encryption,

    transmission, and inquiry polling.
    """

    def __init__(
        self,
        session_repo: EisSessionRepository = Depends(),
        transmission_repo: EisTransmissionRepository = Depends(),
        item_repo: EisTransmissionItemRepository = Depends(),
    ):
        self._session_repo = session_repo
        self._transmission_repo = transmission_repo
        self._item_repo = item_repo

    # ─────────────────────────────────────────────────────────────────────────
    # 1. HELPERS & AUTHENTICATION
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_submit_id(self, now: Optional[datetime] = None) -> str:
        """Generate unique BIR submitId: {accreditationId}-{YYYYMMDD}-{hex12}."""
        dt = now or datetime.now(timezone.utc)
        ymd = dt.strftime("%Y%m%d")
        random_hex = secrets.token_hex(6)  # 12 hex characters
        acc_id = settings.EIS_ACCREDITATION_ID or "NOACC"
        return f"{acc_id}-{ymd}-{random_hex}"

    def _verify_config(self) -> None:
        """Verify mandatory BIR EIS credentials are configured."""
        missing = []
        if not settings.EIS_ENDPOINT_BASE_URL:
            missing.append("EIS_ENDPOINT_BASE_URL")
        if not settings.EIS_USER_ID:
            missing.append("EIS_USER_ID")
        if not settings.EIS_PASSWORD:
            missing.append("EIS_PASSWORD")
        if not settings.EIS_ACCREDITATION_ID:
            missing.append("EIS_ACCREDITATION_ID")
        if not settings.EIS_APPLICATION_ID:
            missing.append("EIS_APPLICATION_ID")
        if not settings.EIS_APPLICATION_SECRET_KEY:
            missing.append("EIS_APPLICATION_SECRET_KEY")
        if not settings.EIS_PUBLIC_KEY:
            missing.append("EIS_PUBLIC_KEY")
        if not settings.EIS_PRIVATE_KEY:
            missing.append("EIS_PRIVATE_KEY")

        if missing:
            raise InternalServerException(
                message=f"Missing required BIR EIS environment configuration: {', '.join(missing)}",
                error_code="EIS_CONFIG_INCOMPLETE",
            )

    async def _ensure_bir_session(self) -> EisSession:
        """Fetch cached active session or authenticate anew if expired.

        Fixes Node.js bug: compares token_expiry against current UTC time.
        """
        active_session = await self._session_repo.get_active_session()
        now_utc = datetime.now(timezone.utc)

        if active_session and active_session.token_expiry > now_utc:
            return active_session

        logger.info("Active BIR EIS session missing or expired. Initiating authentication.")
        return await self._bir_authorize()

    async def _bir_authorize(self) -> EisSession:
        """Authenticate with BIR EIS /api/{v}/authentication.

        Generates fresh authKey, RSA-encrypts credentials, HMAC-signs request,
        and decrypts response session token and AES session key.
        """
        self._verify_config()
        auth_key = generate_auth_key()

        auth_payload = {
            "userId": settings.EIS_USER_ID,
            "password": settings.EIS_PASSWORD,
            "authKey": auth_key,
        }

        encrypted_data = rsa_encrypt(json.dumps(auth_payload), settings.EIS_PUBLIC_KEY)
        dt_str = format_datetime()
        url_path = f"/api/{settings.EIS_API_VERSION}/authentication"
        signature_val = f"{dt_str}POST{url_path}"
        signature = hmac_sign(signature_val, settings.EIS_APPLICATION_SECRET_KEY)

        headers = {
            "accreditationId": settings.EIS_ACCREDITATION_ID,
            "applicationId": settings.EIS_APPLICATION_ID,
            "authorization": f"Bearer {signature}",
            "datetime": dt_str,
        }

        body = {
            "data": encrypted_data,
            "forceRefreshToken": True,
        }

        base_url = settings.EIS_ENDPOINT_BASE_URL.rstrip("/")
        full_url = f"{base_url}{url_path}"

        logger.info(f"Sending BIR EIS auth request to {full_url}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(full_url, json=body, headers=headers)
                resp_data = response.json()
            except Exception as e:
                logger.error(f"BIR EIS authentication network error: {e}")
                raise InternalServerException(
                    message=f"Failed to connect to BIR EIS authentication service: {e}",
                    error_code="EIS_AUTH_NETWORK_ERROR",
                )

        if response.status_code != 200 or resp_data.get("errorDetails"):
            err_msg = (resp_data.get("errorDetails") or {}).get("errorMessage") or response.text
            err_code = (resp_data.get("errorDetails") or {}).get("errorCode") or "EIS_AUTH_FAILED"
            logger.error(f"BIR EIS auth rejected: [{err_code}] {err_msg}")
            raise BadRequestException(
                message=f"BIR EIS authentication failed: {err_msg}",
                error_code=err_code,
            )

        encrypted_resp_data = resp_data.get("data")
        if not encrypted_resp_data:
            raise InternalServerException(
                message="BIR EIS returned 200 OK but payload was empty",
                error_code="EIS_AUTH_EMPTY_PAYLOAD",
            )

        try:
            decrypted_str = aes_decrypt(encrypted_resp_data, auth_key)
            token_data = json.loads(decrypted_str)
        except Exception as e:
            logger.error(f"Failed to decrypt BIR EIS auth response: {e}")
            raise InternalServerException(
                message="Failed to decrypt BIR EIS authentication token payload",
                error_code="EIS_AUTH_DECRYPT_ERROR",
            )

        auth_token = token_data["authToken"]
        session_key = token_data["sessionKey"]
        expiry_raw = token_data["tokenExpiry"]

        # Parse expiry datetime
        try:
            if isinstance(expiry_raw, (int, float)):
                token_expiry = datetime.fromtimestamp(expiry_raw / 1000, tz=timezone.utc)
            else:
                token_expiry = datetime.fromisoformat(str(expiry_raw)).replace(tzinfo=timezone.utc)
        except Exception:
            token_expiry = datetime.now(timezone.utc)

        saved_session = await self._session_repo.create_session(
            auth_token=auth_token,
            session_key=session_key,
            token_expiry=token_expiry,
        )
        logger.info(f"BIR EIS session authenticated successfully. Expiry: {token_expiry}")
        return saved_session

    # ─────────────────────────────────────────────────────────────────────────
    # 2. TRANSMISSION GATEWAY
    # ─────────────────────────────────────────────────────────────────────────

    async def transmit_cas_invoices(
        self,
        invoices: List[EisCasInvoice],
        parent_transmission_id: Optional[uuid.UUID] = None,
    ) -> EisTransmitResponse:
        """Validate, sign, encrypt, and transmit a batch of CAS invoices to BIR EIS."""
        self._verify_config()
        if not invoices:
            raise BadRequestException(
                message="Cannot transmit empty invoice list",
                error_code="EIS_EMPTY_BATCH",
            )

        # Step 1: Pre-process with mixed-tax splitter (BIR Section 5 compliance)
        processed_invoices: List[EisCasInvoice] = []
        for inv in invoices:
            processed_invoices.extend(check_mixed_tax_split(inv))

        # Step 2: Ensure active session
        session = await self._ensure_bir_session()

        # Step 3: Generate submitId
        submit_id = self._generate_submit_id()

        # Step 4: Sign each invoice with RS256 JWS
        signed_tokens: List[str] = []
        for inv in processed_invoices:
            inv_json = inv.model_dump_json(by_alias=True)
            token = jws_sign(
                payload_json_str=inv_json,
                private_key_b64=settings.EIS_PRIVATE_KEY,
                key_id=settings.EIS_APPLICATION_KEY_ID or "default-key",
            )
            signed_tokens.append(token)

        # Step 5: Comma-join signed JWS tokens and AES encrypt with sessionKey
        signed_blob = ",".join(signed_tokens)
        encrypted_payload = aes_encrypt(signed_blob, session.session_key)

        # Step 6: Create EisTransmission audit record
        submitted_at = datetime.now(timezone.utc)
        transmission = await self._transmission_repo.create(
            {
                "submit_id": submit_id,
                "parent_transmission_id": parent_transmission_id,
                "status": EisTransmissionStatus.PENDING,
                "invoice_count": len(processed_invoices),
                "raw_request": encrypted_payload,  # Encrypted only, no plaintext
                "submitted_at": submitted_at,
            },
            commit=True,
        )

        # Step 7: Transmit payload to BIR EIS /api/{v}/invoices
        dt_str = format_datetime()
        url_path = f"/api/{settings.EIS_API_VERSION}/invoices"
        signature_val = f"{dt_str}POST{url_path}"
        signature = hmac_sign(signature_val, session.session_key)

        headers = {
            "accreditationId": settings.EIS_ACCREDITATION_ID,
            "applicationId": settings.EIS_APPLICATION_ID,
            "authToken": session.auth_token,
            "authorization": f"Bearer {signature}",
            "datetime": dt_str,
        }

        body = {
            "submitId": submit_id,
            "data": encrypted_payload,
        }

        base_url = settings.EIS_ENDPOINT_BASE_URL.rstrip("/")
        full_url = f"{base_url}{url_path}"

        logger.info(f"Submitting batch {submit_id} ({len(processed_invoices)} invoices) to BIR EIS")
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(full_url, json=body, headers=headers)
                resp_data = response.json()
            except Exception as e:
                logger.error(f"Transmission HTTP error for submit_id {submit_id}: {e}")
                await self._transmission_repo.update_status(
                    transmission,
                    status=EisTransmissionStatus.FAILED,
                    raw_response=str(e),
                )
                raise InternalServerException(
                    message=f"BIR EIS invoice submission network error: {e}",
                    error_code="EIS_TRANSMIT_NETWORK_ERROR",
                )

        raw_resp_str = json.dumps(resp_data)
        if response.status_code != 200 or resp_data.get("errorDetails"):
            err_msg = (resp_data.get("errorDetails") or {}).get("errorMessage") or response.text
            err_code = (resp_data.get("errorDetails") or {}).get("errorCode") or "EIS_SUBMIT_FAILED"
            logger.error(f"BIR EIS rejected submission {submit_id}: [{err_code}] {err_msg}")
            await self._transmission_repo.update_status(
                transmission,
                status=EisTransmissionStatus.FAILED,
                raw_response=raw_resp_str,
            )
            raise BadRequestException(
                message=f"BIR EIS transmission rejected: {err_msg}",
                error_code=err_code,
            )

        # Decrypt response data to extract ackId
        ack_id: Optional[str] = None
        encrypted_resp = resp_data.get("data")
        if encrypted_resp:
            try:
                decrypted_json = aes_decrypt(encrypted_resp, session.session_key)
                ack_data = json.loads(decrypted_json)
                ack_id = ack_data.get("ackId")
            except Exception as e:
                logger.warning(f"Could not decrypt transmission response payload: {e}")

        # Update status to SENT
        transmission = await self._transmission_repo.update_status(
            transmission,
            status=EisTransmissionStatus.SENT,
            ack_id=ack_id,
            raw_response=raw_resp_str,
        )

        # Enqueue submit_id to Redis worker for durable background inquiry polling
        try:
            from modules.eis.eis_worker import enqueue_inquiry
            await enqueue_inquiry(submit_id)
        except Exception as e:
            logger.warning(f"Could not enqueue submit_id '{submit_id}' to Redis worker: {e}")

        return EisTransmitResponse(
            id=transmission.id,
            submit_id=transmission.submit_id,
            status=transmission.status,
            ack_id=transmission.ack_id,
            invoice_count=transmission.invoice_count,
            submitted_at=transmission.submitted_at,
            response_details=SchemaResponseDetails(
                status=True,
                description=f"Invoices submitted to BIR EIS. Awaiting inquiry acknowledgement.",
                count=transmission.invoice_count,
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. INQUIRY POLLING & STATUS
    # ─────────────────────────────────────────────────────────────────────────

    async def poll_inquiry_for_submit_id(self, submit_id: str) -> bool:
        """Poll BIR EIS /api/{v}/invoice_result/{submitId} and update transmission audit records.

        Adheres strictly to BIR EIS API Development Guide Section 7.3.3 (Pages 40-44):
        - Parses 'processedDocuments' array containing invoiceUid, resultStatusCode, description.
        - Uses EisResultStatus.from_bir_code to safely classify SUC001, SYN002-4, ERR001-7.
        - Handles processStatusCode '01' (Completed), '02' (In processing), '03' (Unable to process).

        Returns:
            True if transmission reached terminal state (ACKNOWLEDGED, PARTIAL, FAILED).
            False if still in PROCESSING ('02') or transient error that should be retried.
        """
        transmission = await self._transmission_repo.get_by_submit_id(submit_id)
        if not transmission:
            logger.warning(f"Transmission with submit_id '{submit_id}' not found in database.")
            return True

        if transmission.status in (
            EisTransmissionStatus.ACKNOWLEDGED,
            EisTransmissionStatus.FAILED,
            EisTransmissionStatus.PARTIAL,
        ):
            return True

        self._verify_config()
        session = await self._ensure_bir_session()
        dt_str = format_datetime()
        url_path = f"/api/{settings.EIS_API_VERSION}/invoice_result/{submit_id}"
        signature_val = f"{dt_str}GET{url_path}"
        signature = hmac_sign(signature_val, session.session_key)

        headers = {
            "accreditationId": settings.EIS_ACCREDITATION_ID,
            "applicationId": settings.EIS_APPLICATION_ID,
            "authToken": session.auth_token,
            "authorization": f"Bearer {signature}",
            "datetime": dt_str,
        }

        base_url = settings.EIS_ENDPOINT_BASE_URL.rstrip("/")
        full_url = f"{base_url}{url_path}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(full_url, headers=headers)
                resp_data = response.json()
        except Exception as e:
            logger.error(f"Network error during inquiry poll for submit_id {submit_id}: {e}")
            return False

        if response.status_code != 200 or resp_data.get("errorDetails"):
            err_details = resp_data.get("errorDetails") or {}
            err_code = err_details.get("errorCode") or "UNKNOWN_ERR"
            err_msg = err_details.get("errorMessage") or response.text
            logger.warning(f"Inquiry poll returned error for {submit_id}: [{err_code}] {err_msg}")
            if err_code in ("E15", "E16", "E01", "E02"):
                await self._transmission_repo.update_status(
                    transmission,
                    status=EisTransmissionStatus.FAILED,
                    raw_response=json.dumps(resp_data),
                )
                return True
            return False

        inquiry_data = resp_data.get("data") or {}
        process_code = inquiry_data.get("processStatusCode")

        if process_code == EisProcessStatus.COMPLETED.value:
            logger.info(f"BIR EIS processing COMPLETED ('01') for {submit_id}")
            # BIR spec uses 'processedDocuments' (Section 7.3.3.4, P. 41)
            processed_docs = (
                inquiry_data.get("processedDocuments")
                or inquiry_data.get("resultList")
                or []
            )

            items_to_create = []
            has_error = False
            has_success = False

            for res in processed_docs:
                uid = res.get("invoiceUid") or res.get("eisUniqueId") or ""
                res_code = res.get("resultStatusCode") or res.get("resultStatus") or ""
                res_status = EisResultStatus.from_bir_code(res_code)
                fail_desc = res.get("description") or res.get("failMessage")

                if res_status == EisResultStatus.SUCCESS:
                    has_success = True
                else:
                    has_error = True

                items_to_create.append(
                    {
                        "transmission_id": transmission.id,
                        "eis_unique_id": uid,
                        "comp_invoice_id": res.get("compInvoiceId"),
                        "result_status": res_status,
                        "fail_reason_code": res_code,
                        "fail_message": fail_desc,
                    }
                )

            if items_to_create:
                await self._item_repo.bulk_create(items_to_create)

            final_status = EisTransmissionStatus.ACKNOWLEDGED
            if has_error and has_success:
                final_status = EisTransmissionStatus.PARTIAL
            elif has_error and not has_success:
                final_status = EisTransmissionStatus.FAILED

            await self._transmission_repo.update_status(
                transmission,
                status=final_status,
                process_status_code=process_code,
                raw_response=json.dumps(resp_data),
                acknowledged_at=datetime.now(timezone.utc),
            )
            return True

        elif process_code == EisProcessStatus.PROCESSING.value:
            logger.debug(f"BIR EIS batch {submit_id} is in PROCESSING ('02') state.")
            return False

        elif process_code == EisProcessStatus.UNABLE_TO_PROCESS.value:
            fail_reason = inquiry_data.get("failReasonStatusCode") or "UNABLE_TO_PROCESS"
            logger.error(f"BIR EIS unable to process batch {submit_id}: [{fail_reason}]")
            await self._transmission_repo.update_status(
                transmission,
                status=EisTransmissionStatus.FAILED,
                process_status_code=process_code,
                raw_response=json.dumps(resp_data),
                acknowledged_at=datetime.now(timezone.utc),
            )
            return True
        else:
            logger.warning(f"Unexpected processStatusCode '{process_code}' for {submit_id}")
            return False

    async def get_transmission_status(self, submit_id: str) -> EisInquiryResponse:
        """Fetch transmission record and individual item results from audit DB."""
        transmission = await self._transmission_repo.get_by_submit_id(submit_id)
        if not transmission:
            raise NotFoundException(
                message=f"Transmission with submitId '{submit_id}' not found",
                error_code="EIS_TRANSMISSION_NOT_FOUND",
            )

        items_resp = [
            EisTransmissionItemResponse(
                id=item.id,
                eis_unique_id=item.eis_unique_id,
                comp_invoice_id=item.comp_invoice_id,
                result_status=item.result_status,
                fail_reason_code=item.fail_reason_code,
                fail_message=item.fail_message,
                created_at=item.created_at,
            )
            for item in transmission.items
        ]

        return EisInquiryResponse(
            id=transmission.id,
            submit_id=transmission.submit_id,
            status=transmission.status,
            ack_id=transmission.ack_id,
            invoice_count=transmission.invoice_count,
            process_status_code=transmission.process_status_code,
            submitted_at=transmission.submitted_at,
            acknowledged_at=transmission.acknowledged_at,
            items=items_resp,
            response_details=SchemaResponseDetails(
                status=True,
                description=f"Retrieved audit status for {submit_id}",
                count=len(items_resp),
            ),
        )

    async def get_transmissions_paginated(
        self,
        status: Optional[EisTransmissionStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[EisTransmitResponse], int]:
        """Fetch paginated audit transmission records."""
        records, total = await self._transmission_repo.get_transmissions_paginated(
            status=status,
            limit=limit,
            offset=offset,
        )

        responses = [
            EisTransmitResponse(
                id=rec.id,
                submit_id=rec.submit_id,
                status=rec.status,
                ack_id=rec.ack_id,
                invoice_count=rec.invoice_count,
                submitted_at=rec.submitted_at,
                response_details=SchemaResponseDetails(
                    status=True,
                    description="Audit transmission log record",
                    count=rec.invoice_count,
                ),
            )
            for rec in records
        ]

        return responses, total
