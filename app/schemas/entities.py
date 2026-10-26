from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


Role = Literal["administrator", "teacher", "student"]
TransactionStatus = Literal["pending", "approved", "rejected", "borrowed", "returned"]


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: Role
    is_active: bool


class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    category: str | None = Field(default=None, max_length=80)
    quantity: int = Field(default=0, ge=0)
    is_available: bool = False


class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    category: str | None = Field(default=None, max_length=80)
    quantity: int | None = Field(default=None, ge=0)
    is_available: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "ResourceUpdate":
        for field in ("name", "quantity", "is_available"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    category: str | None
    quantity: int
    is_available: bool


class ResourceTransactionCreate(BaseModel):
    user_id: int = Field(gt=0)
    resource_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class ResourceTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    resource_id: int
    quantity: int
    status: TransactionStatus
    borrowed_at: datetime | None
    returned_at: datetime | None
