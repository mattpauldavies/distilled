import uuid
from datetime import datetime

from pydantic import BaseModel


class EnvironmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_production: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateEnvironmentRequest(BaseModel):
    is_production: bool
