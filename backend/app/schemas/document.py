from typing import TypedDict, Optional, Literal, List
import datetime as dt
import uuid
from pydantic import BaseModel, Field, field_validator

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
    expected_type: Optional[str]
    ingestion_method: Optional[str]
    ingestion_logs: Optional[dict]
    extracted_data: Optional[FinancialDocument]
    error: Optional[str]

# --- DB Response Schemas ---

from app.schemas.tax import TaxAnalysisResponse

class TransactionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    merchant_name: str
    date: dt.date | None = None
    amount: float
    category: Optional[str] = None
    receipt_id: Optional[uuid.UUID] = None
    match_score: Optional[float] = None
    match_type: Optional[str] = None
    tax_analysis: Optional[TaxAnalysisResponse] = None

    class Config:
        from_attributes = True

class FinancialDocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    doc_type: str
    status: str
    created_at: dt.datetime
    raw_text: Optional[str] = None
    linked_transaction_id: Optional[uuid.UUID] = None
    transactions: List[TransactionResponse] = []

    class Config:
        from_attributes = True

class FinancialDocumentUpdate(BaseModel):
    date: dt.date | None = None
    amount: Optional[float] = None
    merchant_name: Optional[str] = None
    status: Optional[str] = None 

    @field_validator('amount', mode='before')
    @classmethod
    def parse_amount(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            clean = v.upper().replace("R$", "").replace(" ", "")
            if "," in clean:
                clean = clean.replace(".", "").replace(",", ".")
            return float(clean)
        return v
    
    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str) and v.strip() != "":
            try:
                if len(v) > 10: v = v[:10]
                return dt.datetime.strptime(v, "%Y-%m-%d").date()
            except ValueError:
                pass
        return v
