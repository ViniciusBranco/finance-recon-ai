from typing import Optional, TypedDict
from pydantic import BaseModel, Field

class ReceiptData(BaseModel):
    merchant_name: str = Field(description="Name of the merchant or establishment")
    date: str = Field(description="Date of transaction in YYYY-MM-DD format")
    total_amount: float = Field(description="Total amount of the transaction")
    cnpj: Optional[str] = Field(default=None, description="CNPJ of the merchant")
    category: Optional[str] = Field(default=None, description="Category of the expense (e.g., Food, Transport)")

class ExtractionState(TypedDict):
    file_path: str
    raw_text: Optional[str]
    structured_data: Optional[ReceiptData]
    error: Optional[str]
