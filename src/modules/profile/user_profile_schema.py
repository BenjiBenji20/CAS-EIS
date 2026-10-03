from datetime import date
from uuid import UUID

from base.schema import BaseSchema


class UserProfileResponse(BaseSchema):
    user_id: UUID
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    suffix: str | None = None
    nickname: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    cellphone_number: str | None = None
    street: str | None = None
    city: str | None = None
    province_state: str | None = None
    postal_code: str | None = None
    country: str | None = None
