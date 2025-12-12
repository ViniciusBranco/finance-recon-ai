from pydantic import BaseModel
from uuid import UUID

class ManualMatchRequest(BaseModel):
    receipt_id: UUID
    force: bool = False
