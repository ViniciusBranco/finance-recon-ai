import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Text, Date, Float, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

class Base(DeclarativeBase):
    pass

class FinancialDocument(Base):
    __tablename__ = "financial_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False, server_default="unknown.pdf")
    file_hash: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    doc_type: Mapped[str] = mapped_column(String, nullable=False) # RECEIPT, BANK_STATEMENT, UNKNOWN
    status: Mapped[str] = mapped_column(String, default="PROCESSED") # PROCESSED, REQUIRES_REVIEW, MANUAL_EDITED
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ingestion_method: Mapped[Optional[str]] = mapped_column(String, nullable=True) # FAST_TRACK, LLM_FALLBACK
    ingestion_logs: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Competence Tracking
    competence_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competence_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="document", 
        cascade="all, delete-orphan",
        foreign_keys="[Transaction.document_id]"
    )

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financial_documents.id"), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Competence Tracking & Locking
    competence_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competence_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False)

    # Reconciliation fields
    receipt_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("financial_documents.id"), nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_type: Mapped[Optional[str]] = mapped_column(String, nullable=True) # AUTO, MANUAL

    document: Mapped["FinancialDocument"] = relationship(foreign_keys=[document_id], back_populates="transactions")
    receipt: Mapped[Optional["FinancialDocument"]] = relationship(foreign_keys=[receipt_id])
    
    tax_analysis: Mapped[Optional["TaxAnalysis"]] = relationship(
        back_populates="transaction",
        uselist=False,
        cascade="all, delete-orphan"
    )



class TaxAnalysis(Base):
    __tablename__ = "tax_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"), unique=True, nullable=False)
    
    classification: Mapped[str] = mapped_column(String, nullable=False) # Dedutível, Não Dedutível, Parcialmente Dedutível
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    month: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    justification_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legal_citation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_analysis: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Token Tracking
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_cost_brl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Audit fields
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    transaction: Mapped["Transaction"] = relationship(back_populates="tax_analysis")

class TaxReport(Base):
    __tablename__ = "tax_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    total_deductible: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
