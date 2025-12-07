from typing import TypedDict, Optional, Literal, List
from datetime import datetime, date
import uuid
from pydantic import BaseModel, Field

class FinancialDocument(BaseModel):
    file_name: str = Field(description="Name of the processed file")
    doc_type: Literal["RECEIPT", "BANK_STATEMENT", "UNKNOWN"] = Field(description="Type of the financial document")
    date: Optional[str] = Field(default=None, description="Date of the transaction or statement in YYYY-MM-DD")
    amount: Optional[float] = Field(default=None, description="Total amount or final balance")
    merchant_or_bank: Optional[str] = Field(default=None, description="Name of the merchant or bank")
    raw_content: Optional[str] = Field(default=None, description="Raw extracted text content for debugging")
    transactions: Optional[list[dict]] = Field(default=None, description="List of extracted transactions for statements")

class ProcessingState(TypedDict):
    file_path: str
    password: Optional[str]
    file_extension: str
    extracted_data: Optional[FinancialDocument]
    error: Optional[str]

# --- DB Response Schemas ---

class TransactionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    merchant_name: str
    date: date
    amount: float
    category: Optional[str] = None
    receipt_id: Optional[uuid.UUID] = None
    match_score: Optional[float] = None
    match_type: Optional[str] = None

    class Config:
        from_attributes = True

class FinancialDocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    doc_type: str
    status: str
    created_at: datetime
    raw_text: Optional[str] = None
    transactions: List[TransactionResponse] = []

    class Config:
        from_attributes = True
