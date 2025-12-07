import os
import uuid
import aiofiles
import hashlib
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from fastapi.concurrency import run_in_threadpool
from app.services.processor import process_document
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from typing import List
from app.db.session import get_db
from app.db.models import FinancialDocument, Transaction
from app.schemas.document import FinancialDocumentResponse, TransactionResponse

router = APIRouter()

UPLOAD_DIR = "/tmp/uploads"

@router.post("/upload", summary="Upload and process a financial document")
async def upload_document(
    file: UploadFile = File(...),
    password: str | None = Form(None),
    expected_type: str | None = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a file, checks for duplicates, and triggers processing.
    """
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    # 1. Calculate Hash & Check Deduplication
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    
    stmt = select(FinancialDocument).where(FinancialDocument.file_hash == file_hash)
    existing_doc = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate file. Document already exists with ID: {existing_doc.id}"
        )

    # 2. Save File
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(content)

        # 3. Process
        result = await process_document(
            file_path, 
            password, 
            file_hash=file_hash, 
            original_filename=file.filename,
            expected_type=expected_type
        )
        
        doc_id = result.get("doc_id")
        
        if result.get("error"):
            if result["error"] in ["PASSWORD_REQUIRED", "Invalid Password"]:
                 raise HTTPException(status_code=400, detail=result["error"])
            
            # Persist generic parsing errors without 500
            return {
                "message": "File uploaded but parsing failed",
                "file_id": doc_id,
                "original_filename": file.filename,
                "error": result["error"],
                "status": "partial_success"
            }

        extracted = result.get("extracted_data")
        txn_count = 0
        doc_type = "UNKNOWN"
        
        if extracted:
            doc_type = extracted.doc_type
            # Trust expected_type if provided
            if expected_type:
                doc_type = expected_type

            if extracted.transactions:
                txn_count = len(extracted.transactions)
            elif doc_type == "RECEIPT": 
                txn_count = 1

        message = "Success"
        if doc_type == "BANK_STATEMENT" and txn_count == 0:
            message = "File uploaded, but no transactions could be parsed."

        return {
            "message": message,
            "file_id": doc_id,
            "original_filename": file.filename,
            "transactions_extracted": txn_count,
            "doc_type": doc_type
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal processing error: {str(e)}")

@router.post("/reconcile")
async def reconcile_transactions():
    """
    Triggers the automatic reconciliation process.
    Matches Bank Transactions with Receipts based on Amount, Date, and Merchant.
    """
    from app.services.reconciler import ReconciliationEngine
    from app.db.session import AsyncSessionLocal
    
    engine = ReconciliationEngine()
    async with AsyncSessionLocal() as session:
        stats = await engine.run_auto_reconciliation(session)
        return stats

@router.get("/documents", response_model=List[FinancialDocumentResponse])
async def get_documents(
    doc_type: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all financial documents with their transactions.
    Optional: Filter by doc_type (e.g., 'RECEIPT', 'BANK_STATEMENT').
    """
    stmt = select(FinancialDocument).options(selectinload(FinancialDocument.transactions))
    
    if doc_type:
        stmt = stmt.where(FinancialDocument.doc_type == doc_type)
        
    stmt = stmt.order_by(FinancialDocument.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    unlinked_only: bool = False,
    doc_type: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all transactions.
    If unlinked_only=True, returns only transactions not yet matched to a receipt.
    If doc_type is provided, filters transactions by their parent document's type.
    """
    stmt = select(Transaction).join(FinancialDocument, Transaction.document_id == FinancialDocument.id)
    
    if unlinked_only:
        stmt = stmt.where(Transaction.receipt_id.is_(None))
        
    if doc_type:
        stmt = stmt.where(FinancialDocument.doc_type == doc_type)
        
    stmt = stmt.order_by(Transaction.date.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a document and cleanup its relationships.
    If it's a Receipt that was matched to a transaction, unmatch the transaction.
    Also removes the physical file.
    """
    doc = await db.get(FinancialDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Unlink any transactions that reference this document as a receipt
    stmt = (
        update(Transaction)
        .where(Transaction.receipt_id == document_id)
        .values(receipt_id=None, match_score=None, match_type=None)
    )
    await db.execute(stmt)

    # Remove physical file
    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass 

    # Delete the document 
    await db.delete(doc)
    await db.commit()
    return None

@router.delete("/reset", status_code=status.HTTP_200_OK)
async def reset_workspace(db: AsyncSession = Depends(get_db)):
    """
    DANGER: Resets the entire workspace.
    Deletes ALL transactions and documents.
    """
    try:
        # 1. Delete all Transactions
        await db.execute(delete(Transaction))
        
        # 2. Delete all Documents
        await db.execute(delete(FinancialDocument))
        
        await db.commit()
        
        # 3. Clear Uploads Directory
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception:
                    pass
                    
        return {"message": "Workspace cleared"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
