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
            txn.tax_analysis.risk_level = analysis_result.risco_glosa
            txn.tax_analysis.raw_analysis = analysis_result.model_dump(mode='json')
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
                risk_level=analysis_result.risco_glosa,
                raw_analysis=analysis_result.model_dump(mode='json'),
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

@router.post("/tax-analysis/batch")
async def batch_analyze_transactions(
    db: AsyncSession = Depends(get_db)
):
    """
    Batch analyzes all pending transactions (with receipt but without analysis).
    Rate limit: 1 request/second to respect Gemini Free Tier.
    """
    import asyncio
    
    # 1. Find pending transactions
    # Join receipt (must have one) and ensure no tax_analysis exists
    stmt = (
        select(Transaction)
        .options(
            selectinload(Transaction.receipt)
        )
        .outerjoin(TaxAnalysis)
        .where(
            Transaction.receipt_id.is_not(None),
            TaxAnalysis.id.is_(None) # Ensure no analysis linked
        )
    )
    
    result = await db.execute(stmt)
    pending_txns = result.scalars().all()
    
    processed_count = 0
    total_cost_brl = 0.0
    
    print(f"Batch Analysis: Found {len(pending_txns)} pending transactions.")
    
    for txn in pending_txns:
        try:
            # 2. Prepare Data
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
                receipt_content = f"Receipt file: {txn.receipt.original_filename}"
            else:
                receipt_content = "Nenhum comprovante vinculado."
            
            # 3. Analyze
            analysis_result = await tax_agent.analyze_transaction(transaction_data, receipt_content)
            
            # 4. Save
            # Create object (Logic Guard handled inside agent, but persistence here ensures we handle 'estimated_cost' if agent returns it? 
            # Wait, Agent ALREADY persists to DB if we pass db_session!
            # Let's check agent signature: analyze_transaction(..., db_session=None).
            # If we pass db, it saves.
            
            # BUT, we are in a loop. We should pass the session.
            # However agent commits or flushes? Agent calls `flush`.
            # We must commit at the end or per item.
            
            # Wait, `tax_agent.analyze_transaction` (lines 162+) accepts `db_session`.
            # If passed, it adds and flushes (lines 291-293).
            
            # Let's pass `db` to agent.
            # But wait, we need to read the COST from the created analysis to aggregate `total_cost_brl`.
            # The agent returns `TaxAnalysisResult` (Pydantic), which doesn't have the cost fields we added to DB model.
            
            # We can re-query the TaxAnalysis from DB buffer since it was flushed?
            # Or we can rely on standard logging.
            
            # To get cost for return summary, we might need to modify agent to return cost or wrapper.
            # Or just query the DB after flush.
             
            # Let's do:
            async with db.begin_nested(): # Savepoint if needed, or just standard flow
                # Actually agent uses `db_session.add`.
                pass
                
            # We'll rely on the agent to save.
            # We won't get cost easily from `analysis_result` (Pydantic).
            # We can check the DB for the newly created record using txn.id.
            
            await tax_agent.analyze_transaction(transaction_data, receipt_content, db_session=db)
            
            # Retrieve cost for summary
            # Since flush happened, we can query it.
            # Or inspect `db.new` ?
            # simpler: Query.
            
            # We need to commit to persist? Agent only flushes.
            await db.commit() 
            
            # Get cost
            analysis_check = await db.execute(select(TaxAnalysis).where(TaxAnalysis.transaction_id == txn.id))
            created_analysis = analysis_check.scalar_one_or_none()
            if created_analysis and created_analysis.estimated_cost_brl:
                total_cost_brl += created_analysis.estimated_cost_brl

            processed_count += 1
            
            # 5. Rate Limit (Gemini Free Tier: 5 RPM -> ~13s interval)
            # Only sleep if we have more items to process
            if processed_count < len(pending_txns):
                await asyncio.sleep(13)
                
        except Exception as e:
            err_str = str(e)
            print(f"Error processing txn {txn.id}: {e}")
            
            # Check for Rate Limit (429)
            if "429" in err_str or "ResourceExhausted" in err_str or "Quota" in err_str:
                print(f"RATE LIMIT HIT. Stopping batch.")
                return {
                    "processed": processed_count,
                    "total_cost_brl": total_cost_brl,
                    "message": f"Stopped early due to Rate Limit (processed {processed_count} items)."
                }
            
            # Continue to next if other error
            continue
            
    return {
        "processed": processed_count,
        "total_cost_brl": total_cost_brl,
        "message": f"Successfully analyzed {processed_count} transactions."
    }
