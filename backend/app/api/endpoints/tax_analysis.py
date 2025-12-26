from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
import uuid
from app.db.session import get_db
from app.db.models import Transaction, FinancialDocument, TaxAnalysis
from app.services.tax_agent import tax_agent
from app.schemas.tax import TaxAnalysisResult, TaxAnalysisResponse, TaxAnalysisUpdate

router = APIRouter()

@router.post("/tax-analysis/{transaction_id}", response_model=TaxAnalysisResponse)
async def analyze_transaction_tax(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Analyzes a transaction for tax deductibility.
    If a manual override exists, returns it without re-analyzing.
    Otherwise, runs the AI agent and saves the result.
    """
    # 1. Fetch transaction with receipt and existing analysis
    stmt = (
        select(Transaction)
        .options(
            selectinload(Transaction.receipt),
            selectinload(Transaction.tax_analysis)
        )
        .where(Transaction.id == transaction_id)
    )
    result = await db.execute(stmt)
    txn = result.scalar_one_or_none()

    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # 2. Check for Manual Override
    if txn.tax_analysis and txn.tax_analysis.is_manual_override:
        return txn.tax_analysis

    # 3. Prepare data for Agent
    transaction_data = {
        "id": str(txn.id),
        "date": txn.date.strftime("%Y-%m-%d"),
        "amount": float(txn.amount),
        "merchant": txn.merchant_name,
        "category": txn.category if txn.category else "Uncategorized"
    }

    receipt_content = ""
    if txn.receipt and txn.receipt.raw_text:
        receipt_content = txn.receipt.raw_text
    elif txn.receipt:
        receipt_content = f"Receipt file: {txn.receipt.original_filename} (No text extracted)"
    else:
        receipt_content = "Nenhum comprovante vinculado."

    # 4. Call Agent
    try:
        analysis_result = await tax_agent.analyze_transaction(transaction_data, receipt_content)
        
        # 5. Save/Update DB
        justification = f"{analysis_result.comentario}\n\nChecklist: {analysis_result.checklist}\nRisco: {analysis_result.risco_glosa}"
        
        if txn.tax_analysis:
            # Update existing
            txn.tax_analysis.classification = analysis_result.classificacao
            txn.tax_analysis.category = analysis_result.categoria
            txn.tax_analysis.month = analysis_result.mes_lancamento
            txn.tax_analysis.justification_text = justification
            txn.tax_analysis.legal_citation = analysis_result.citacao_legal
            txn.tax_analysis.is_manual_override = False
        else:
            # Create new
            new_analysis = TaxAnalysis(
                transaction_id=txn.id,
                classification=analysis_result.classificacao,
                category=analysis_result.categoria,
                month=analysis_result.mes_lancamento,
                justification_text=justification,
                legal_citation=analysis_result.citacao_legal,
                is_manual_override=False
            )
            db.add(new_analysis)
            
        await db.commit()
        
        # Refresh to get the object with ID
        if txn.tax_analysis:
             await db.refresh(txn.tax_analysis)
             return txn.tax_analysis
        else:
             # We need to fetch the newly created one to be sure content is synced or just return what we created
             # new_analysis has no ID until after commit/refresh, which we did.
             await db.refresh(new_analysis)
             return new_analysis

    except Exception as e:
        print(f"Tax Agent Error: {e}")
        raise HTTPException(status_code=500, detail=f"Tax Agent Error: {str(e)}")

@router.put("/tax-analysis/{transaction_id}", response_model=TaxAnalysisResponse)
async def update_tax_analysis(
    transaction_id: uuid.UUID,
    update_data: TaxAnalysisUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually updates the tax classification for a transaction.
    Sets is_manual_override = True.
    """
    stmt = (
        select(TaxAnalysis)
        .where(TaxAnalysis.transaction_id == transaction_id)
    )
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        # Create one if it doesn't exist (e.g. manual override before AI run)
        # Check transaction existence first
        txn_check = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
        if not txn_check.scalar_one_or_none():
             raise HTTPException(status_code=404, detail="Transaction not found")
             
        analysis = TaxAnalysis(
            transaction_id=transaction_id,
            classification=update_data.classification,
            category=update_data.category,
            justification_text=update_data.justification_text,
            legal_citation=update_data.legal_citation,
            is_manual_override=True
        )
        db.add(analysis)
    else:
        # Update existing
        analysis.classification = update_data.classification
        analysis.category = update_data.category
        if update_data.justification_text is not None:
            analysis.justification_text = update_data.justification_text
        if update_data.legal_citation is not None:
            analysis.legal_citation = update_data.legal_citation
        
        analysis.is_manual_override = True
    
    await db.commit()
    await db.refresh(analysis)
    return analysis
