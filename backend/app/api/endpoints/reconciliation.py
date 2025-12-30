import os
import uuid
import aiofiles
import hashlib
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Query
from fastapi.concurrency import run_in_threadpool
from app.services.processor import process_document
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from typing import List
from app.db.session import get_db
from app.db.models import FinancialDocument, Transaction, TaxAnalysis, TaxReport
from app.schemas.document import FinancialDocumentResponse, TransactionResponse
from app.schemas.match import ManualMatchRequest
from datetime import date

router = APIRouter()

UPLOAD_DIR = "/tmp/uploads"
EXPORT_DIR = "/app/exports"

async def _handle_upload(
    file: UploadFile, 
    password: str | None, 
    expected_type: str | None, 
    db: AsyncSession,
    month: int | None = None,
    year: int | None = None
):
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
            expected_type=expected_type,
            month=month,
            year=year
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

@router.post("/upload", summary="Upload and process a financial document")
async def upload_document(
    file: UploadFile = File(...),
    password: str | None = Form(None),
    expected_type: str | None = Form(None),
    month: int | None = Form(None),
    year: int | None = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Generic upload endpoint."""
    return await _handle_upload(file, password, expected_type, db, month, year)

@router.post("/upload/statement", summary="Upload a Bank Statement")
async def upload_statement(
    file: UploadFile = File(...),
    password: str | None = Form(None),
    month: int | None = Form(None),
    year: int | None = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Specialized endpoint for Bank Statements."""
    return await _handle_upload(file, password, "BANK_STATEMENT", db, month, year)

@router.post("/upload/receipt", summary="Upload a Receipt")
async def upload_receipt(
    file: UploadFile = File(...),
    password: str | None = Form(None),
    month: int | None = Form(None),
    year: int | None = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Specialized endpoint for Receipts (Pix, Boleto, NFe)."""
    return await _handle_upload(file, password, "RECEIPT", db, month, year)

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
    tax_status: str | None = Query(None, description="Filter by Tax Status (via linked transaction): DEDUCTIBLE, NON_DEDUCTIBLE, PARTIAL"),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all financial documents with their transactions.
    Optional: Filter by doc_type (e.g., 'RECEIPT', 'BANK_STATEMENT').
    """
    stmt = select(FinancialDocument).options(
        selectinload(FinancialDocument.transactions).selectinload(Transaction.tax_analysis)
    )
    
    if doc_type:
        stmt = stmt.where(FinancialDocument.doc_type == doc_type)

    if tax_status:
        # Filter documents (receipts) that are linked to a transaction with the given tax status
        stmt = stmt.join(Transaction, Transaction.receipt_id == FinancialDocument.id)
        
        if tax_status == "TO_ANALYZE":
             # Items that ARE linked (receipt_id joined above) but HAVE NO Tax Analysis
             stmt = stmt.outerjoin(TaxAnalysis, Transaction.id == TaxAnalysis.transaction_id)
             stmt = stmt.where(TaxAnalysis.id.is_(None))
        else:
             stmt = stmt.join(TaxAnalysis, Transaction.id == TaxAnalysis.transaction_id)
             
             if tax_status == "DEDUCTIBLE":
                stmt = stmt.where(TaxAnalysis.classification == "Dedutível")
             elif tax_status == "NON_DEDUCTIBLE":
                stmt = stmt.where(TaxAnalysis.classification == "Não Dedutível")
             elif tax_status == "PARTIAL":
                stmt = stmt.where(TaxAnalysis.classification.in_(["Parcialmente Dedutível", "Depende"]))
        
    stmt = stmt.order_by(FinancialDocument.created_at.desc())
    result = await db.execute(stmt)
    docs = result.scalars().all()

    # Populate linked_transaction_id for Receipts
    if docs:
        doc_ids = [d.id for d in docs]
        link_stmt = select(Transaction.id, Transaction.receipt_id).where(Transaction.receipt_id.in_(doc_ids))
        link_res = await db.execute(link_stmt)
        # Map receipt_id -> transaction_id
        links = {rid: tid for tid, rid in link_res.all()}
        
        for d in docs:
            # Dynamically attach attribute for Pydantic
            setattr(d, "linked_transaction_id", links.get(d.id))

    return docs

@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    unlinked_only: bool = False,
    doc_type: str | None = None,
    tax_status: str | None = Query(None, description="Filter by Tax Status: DEDUCTIBLE, NON_DEDUCTIBLE, PARTIAL"),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch all transactions.
    If unlinked_only=True, returns only transactions not yet matched to a receipt.
    If doc_type is provided, filters transactions by their parent document's type.
    If tax_status is provided, filters by deduced TaxAnalysis classification.
    """
    stmt = (
        select(Transaction)
        .join(FinancialDocument, Transaction.document_id == FinancialDocument.id)
        .outerjoin(TaxAnalysis, Transaction.id == TaxAnalysis.transaction_id)
        .options(selectinload(Transaction.tax_analysis))
    )
    
    if unlinked_only:
        stmt = stmt.where(Transaction.receipt_id.is_(None))
        
    if doc_type:
        stmt = stmt.where(FinancialDocument.doc_type == doc_type)

    if tax_status:
        if tax_status == "DEDUCTIBLE":
            stmt = stmt.where(TaxAnalysis.classification == "Dedutível")
        elif tax_status == "NON_DEDUCTIBLE":
            stmt = stmt.where(TaxAnalysis.classification == "Não Dedutível")
        elif tax_status == "PARTIAL":
            stmt = stmt.where(TaxAnalysis.classification.in_(["Parcialmente Dedutível", "Depende"]))
        elif tax_status == "TO_ANALYZE":
             stmt = stmt.where(
                 Transaction.receipt_id.is_not(None),
                 TaxAnalysis.id.is_(None)
             )
        
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





from app.schemas.document import FinancialDocumentUpdate

@router.patch("/documents/{document_id}", response_model=FinancialDocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    update_data: FinancialDocumentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually update document details (Date/Amount/Merchant).
    Useful for correcting OCR errors.
    """
    stmt = select(FinancialDocument).options(selectinload(FinancialDocument.transactions)).where(FinancialDocument.id == document_id)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    updated = False
    tx = doc.transactions[0] if doc.transactions else None
    
    if tx:
        if update_data.amount is not None:
             tx.amount = update_data.amount
             updated = True
        if update_data.date is not None:
             tx.date = update_data.date
             updated = True
        
        # Determine if merchant_name is in update_data (it's Pydantic model)
        # Using getattr to be safe if schema not yet updated
        m_name = getattr(update_data, "merchant_name", None)
        if m_name:
             tx.merchant_name = m_name
             updated = True



    else:
        # Create a new transaction if none exists
        if update_data.date and update_data.amount is not None:
            new_txn = Transaction(
                document_id=document_id,
                merchant_name=doc.original_filename or "Manual Entry",
                date=update_data.date,
                amount=update_data.amount,
                category="Manual Override"
            )
            db.add(new_txn)
            updated = True
        elif update_data.date or update_data.amount is not None:
             raise HTTPException(status_code=400, detail="Both Date and Amount are required to create a new transaction entry.")

    if updated:
        doc.status = "MANUAL_EDITED"

    await db.commit()
    
    # Return updated document
    stmt = select(FinancialDocument).options(
        selectinload(FinancialDocument.transactions).selectinload(Transaction.tax_analysis)
    ).where(FinancialDocument.id == document_id)
    
    updated_doc = (await db.execute(stmt)).scalar_one()
    return updated_doc
@router.post("/transactions/{transaction_id}/match")
async def manual_match_transaction(
    transaction_id: uuid.UUID,
    match_request: ManualMatchRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually link a Bank Transaction to a Receipt.
    Checks for discrepancies unless force=True.
    """
    # 1. Fetch Transaction
    print(f"DEBUG: Matching Txn {transaction_id} with Receipt {match_request.receipt_id}")
    txn = await db.get(Transaction, transaction_id)
    if not txn:
        print(f"DEBUG: Transaction ID {transaction_id} NOT FOUND.")
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")

    # 2. Fetch Receipt (with Transactions)
    stmt = select(FinancialDocument).options(selectinload(FinancialDocument.transactions)).where(FinancialDocument.id == match_request.receipt_id)
    receipt_res = await db.execute(stmt)
    receipt = receipt_res.scalar_one_or_none()

    if not receipt:
        # Fallback: Maybe the UI sent the Receipt's Transaction ID?
        print(f"DEBUG: Receipt Doc {match_request.receipt_id} not found. Checking if it is a Transaction ID...")
        stmt_tx = select(Transaction).where(Transaction.id == match_request.receipt_id)
        receipt_tx = (await db.execute(stmt_tx)).scalar_one_or_none()
        
        if receipt_tx and receipt_tx.document_id:
             print(f"DEBUG: Resolved ID {match_request.receipt_id} to Document {receipt_tx.document_id}")
             stmt = select(FinancialDocument).options(selectinload(FinancialDocument.transactions)).where(FinancialDocument.id == receipt_tx.document_id)
             receipt = (await db.execute(stmt)).scalar_one_or_none()
    
    if not receipt:
        print(f"DEBUG: Receipt {match_request.receipt_id} not found in DB (neither as Doc nor Txn).")
        raise HTTPException(status_code=404, detail=f"Receipt {match_request.receipt_id} not found in DB")
        
    if receipt.doc_type != "RECEIPT":
         raise HTTPException(status_code=400, detail="Document provided is not a Receipt")

    # 2.5 Unlink older owner if exists (Steal Logic)
    stmt = select(Transaction).where(Transaction.receipt_id == receipt.id)
    existing_links = (await db.execute(stmt)).scalars().all()
    
    for old_txn in existing_links:
        if old_txn.id != txn.id:
            old_txn.receipt_id = None
            old_txn.match_score = None
            old_txn.match_type = None

    # 3. Validation Logic (if not forced)
    if not match_request.force:
        warnings = []
        
        r_amount = None
        r_date = None
        
        # Use first transaction from receipt if available
        if receipt.transactions:
             r_amount = receipt.transactions[0].amount
             r_date = receipt.transactions[0].date
        
        # If Receipt Amount is known
        if r_amount is not None:
             diff = abs(abs(float(txn.amount)) - abs(float(r_amount)))
             if diff > 0.05:
                 warnings.append(f"Diferença de valor detectada: R$ {abs(float(txn.amount))} vs R$ {abs(float(r_amount))}")
        
        # If Receipt Date is known - IGNORE DATE MISMATCHES FOR MANUAL MATCH
        # We allow manual override of dates (Bank clearing delays etc).
        # if r_date is not None:
        #    ... (Date logic skipped) ...
                
        if warnings:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Discrepancy Detected: " + ", ".join(warnings)
            )

    # 4. Apply Match
    txn.receipt_id = receipt.id
    txn.match_score = 1.0
    txn.match_type = "MANUAL"
    
    # NOTE: We intentionally do NOT trigger tax analysis here. It must be a separate user action.
    await db.commit()
    return {"message": "Match confirmed"}

@router.delete("/clear-workspace", status_code=status.HTTP_200_OK)
async def clear_workspace(
    month: int,
    year: int,
    only_unlinked: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    Clears data for a specific competence month/year.
    - If only_unlinked=True: Deletes only unlinked transactions and unused receipts.
    - If only_unlinked=False: Deletes ALL non-finalized data.
    PROTECTION: Never deletes transactions with is_finalized=True.
    """
    try:
        # 1. Identify Transactions to Delete
        # Conditions:
        # - Matches Competence
        # - NOT Finalized
        # - If only_unlinked: Must be unlinked (receipt_id is None)
        
        stmt_tx = select(Transaction).where(
            Transaction.competence_month == month,
            Transaction.competence_year == year,
            Transaction.is_finalized == False
        )
        
        if only_unlinked:
            stmt_tx = stmt_tx.where(Transaction.receipt_id.is_(None))
            
        txns_to_delete = (await db.execute(stmt_tx)).scalars().all()
        txn_ids = [t.id for t in txns_to_delete]
        
        if txn_ids:
             # Delete Tax Analysis first (cascade should handle, but explicit is safe)
             await db.execute(delete(TaxAnalysis).where(TaxAnalysis.transaction_id.in_(txn_ids)))
             
             # Delete Transactions
             await db.execute(delete(Transaction).where(Transaction.id.in_(txn_ids)))
        
        # 2. Identify Documents to Delete
        # Conditions:
        # - Matches Competence
        # - Has NO remaining transactions (orphaned after above delete) OR has NO finalized transactions?
        # A Document should be deleted if:
        # - It belongs to this competence
        # - It has NO transactions that are 'is_finalized=True'
        # - If only_unlinked: It must NOT be a receipt for any existing transaction?
        
        # Let's find documents in this competence
        stmt_docs = select(FinancialDocument).options(selectinload(FinancialDocument.transactions)).where(
            FinancialDocument.competence_month == month,
            FinancialDocument.competence_year == year
        )
        all_docs = (await db.execute(stmt_docs)).scalars().all()
        
        docs_to_delete = []
        for doc in all_docs:
            # Check 1: Does it have any finalized transactions?
            has_finalized = any(t.is_finalized for t in doc.transactions)
            if has_finalized:
                continue # PROTECT
            
            # Check 2: If only_unlinked, is it a Receipt used by a live transaction?
            if only_unlinked and doc.doc_type == "RECEIPT":
                # Check if any transaction refers to this doc as receipt
                # We need to query DB for this because doc.transactions is 'linked to document_id', not 'linked as receipt_id' (unless backref exists)
                # Transaction model has `receipt` interaction, but backref is not strictly defined in list form on Document for receipt usage in provided models.py (it shows `receipt: Mapped[Optional["FinancialDocument"]]` on Transaction but not `receipt_for` on Doc).
                # So we query:
                stmt_link = select(Transaction.id).where(Transaction.receipt_id == doc.id)
                linked_tx = (await db.execute(stmt_link)).first()
                if linked_tx:
                    continue # Used as receipt, don't delete
            
            # If we are here, it matches competence, has no finalized info, and (if unlinked mode) is not used.
            # But wait, if we are in only_unlinked mode, do we delete the Bank Statement Document itself? 
            # Only if it has NO transactions left?
            # If we deleted some unlinked txns, but others remain (linked ones)?
            # We should only delete doc if it has NO transactions.
            
            # Refresh transactions check since we deleted some in step 1?
            # Alternatively, we can rely on `doc.transactions` if we refresh or re-query.
            # Since we deleted txns, the standard check `any(t.is_finalized ...)` might refer to memory objects. 
            # We should re-check DB count of transactions for this doc.
            
            result = await db.execute(select(Transaction.id).where(Transaction.document_id == doc.id))
            remaining_txns = result.all()
            
            if not remaining_txns:
                 docs_to_delete.append(doc)
            elif not only_unlinked:
                 # If explicit clear (not just unlinked), we delete the doc if all its txns were deleted (which they should be if not finalized)
                 # If remaining_txns exist here, it implies they are finalized (since we filtered finalized in step 1).
                 # So if remaining exists, we keep doc.
                 pass

        for doc in docs_to_delete:
             # Delete file
             file_path = os.path.join(UPLOAD_DIR, doc.filename)
             try:
                 if os.path.exists(file_path):
                     os.unlink(file_path)
             except: pass
             
             await db.delete(doc)
             
        await db.commit()
        
        return {
            "message": "Workspace cleanup complete", 
            "deleted_transactions": len(txns_to_delete),
            "deleted_documents": len(docs_to_delete)
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
