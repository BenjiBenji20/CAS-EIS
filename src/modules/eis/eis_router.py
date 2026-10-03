import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from loguru import logger

from base.schema import PaginatedResponse
from modules.eis.eis_enums import EisTransmissionStatus
from modules.eis.eis_schema import (
    EisInquiryResponse,
    EisTransmissionItemResponse,
    EisTransmitRequest,
    EisTransmitResponse,
)
from modules.eis.eis_service import EisService


router = APIRouter(
    prefix="/api/internal/eis",
    tags=["Internal: EIS Transmission Gateway"],
)


@router.post(
    "/transmit",
    summary="Submit CAS invoices to BIR EIS gateway.",
    status_code=status.HTTP_200_OK,
    response_model=EisTransmitResponse,
)
async def transmit_invoices(
    payload: EisTransmitRequest,
    service: EisService = Depends(),
):
    """Sign, encrypt, and submit a batch of validated CAS invoices to the BIR EIS API."""
    logger.info(f"Received internal transmission request for {len(payload.invoices)} CAS invoice(s).")
    return await service.transmit_cas_invoices(invoices=payload.invoices)


@router.get(
    "/status/{submit_id}",
    summary="Query audit log status and per-invoice results for a submission batch.",
    status_code=status.HTTP_200_OK,
    response_model=EisInquiryResponse,
)
async def get_transmission_status(
    submit_id: str,
    service: EisService = Depends(),
):
    """Retrieve transmission audit record and line items from database."""
    logger.info(f"Querying transmission status for submitId: {submit_id}")
    return await service.get_transmission_status(submit_id=submit_id)


@router.post(
    "/retransmit/{transmission_id}",
    summary="Re-transmit an invoice batch with parent audit chain linkage.",
    status_code=status.HTTP_200_OK,
    response_model=EisTransmitResponse,
)
async def retransmit_batch(
    transmission_id: UUID,
    payload: EisTransmitRequest,
    service: EisService = Depends(),
):
    """Submit a retry transmission with a fresh submitId linked to the original failed transmission."""
    logger.info(f"Re-transmitting invoice batch with parent_transmission_id: {transmission_id}")
    return await service.transmit_cas_invoices(
        invoices=payload.invoices,
        parent_transmission_id=transmission_id,
    )


@router.get(
    "/transmissions",
    summary="List paginated audit transmission logs.",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedResponse[EisTransmitResponse],
)
async def list_transmissions(
    status_filter: Optional[EisTransmissionStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: EisService = Depends(),
):
    """List historical EIS transmission batches with optional status filtering."""
    offset = (page - 1) * size
    items, total = await service.get_transmissions_paginated(
        status=status_filter,
        limit=size,
        offset=offset,
    )
    pages = math.ceil(total / size) if total > 0 else 0

    return PaginatedResponse[EisTransmitResponse](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
