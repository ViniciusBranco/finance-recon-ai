from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, extract, func
from sqlalchemy.orm import selectinload
from app.db.session import AsyncSessionLocal
from app.db.models import Transaction, TaxAnalysis
from datetime import date
import pandas as pd
import io

router = APIRouter()

@router.get("/quota-status")
async def get_quota_status():
    """
    Returns the daily AI analysis quota usage.
    """
    limit = 20
    today = date.today()
    
    async with AsyncSessionLocal() as session:
        # Count analysis records created today
        stmt = (
            select(func.count(TaxAnalysis.id))
            .where(func.date(TaxAnalysis.created_at) == today)
        )
        result = await session.execute(stmt)
        used = result.scalar() or 0
        
        return {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used)
        }

@router.get("/report/livro-caixa")
async def generate_tax_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100)
):
    """
    Generates a CSV report (Carnê-Leão compliant) for a specific month/year.
    Returns a downloadable CSV file.
    """
    async with AsyncSessionLocal() as session:
        # Query Transactions joined with TaxAnalysis
        stmt = (
            select(Transaction)
            .join(TaxAnalysis)
            .options(
                selectinload(Transaction.tax_analysis),
                selectinload(Transaction.receipt)
            )
            .where(
                extract('month', Transaction.date) == month,
                extract('year', Transaction.date) == year,
                TaxAnalysis.classification.in_(["Dedutível", "Parcialmente Dedutível"])
            )
        )
        
        result = await session.execute(stmt)
        transactions = result.scalars().all()
        
        if not transactions:
            # We can either return 404 or an empty CSV. 
            # Returning empty CSV is often better for "No data" reports, 
            # but let's return 404 for clarity if preferred, or just empty.
            # Let's return 404 to inform the user explicitly.
            raise HTTPException(status_code=404, detail=f"No deductible transactions found for {month:02d}/{year}")

        data = []
        
        # Category Map
        CATEGORY_MAP = {
            "Água": "P10.01.00001",
            "Aluguel": "P10.01.00002",
            "Condomínio": "P10.01.00003",
            "Contribuição de Classe": "P10.01.00004", 
            "Emolumentos": "P10.01.00006",
            "Energia": "P10.01.00007",
            "Telefone": "P10.01.00007",
            "Internet": "P10.01.00007",
            "Gás": "P10.01.00008",
            "IPTU": "P10.01.00009",
            "ISS": "P10.01.00010",
            "Limpeza": "P10.01.00011",
            "Material de Consumo": "P10.01.00012",
            "Material de Escritório": "P10.01.00012",
            "Software": "P10.01.00012",
            "Surya Dental": "P10.01.00005", 
            "Material Odonto": "P10.01.00005",
            "Outros": "P10.01.00012"
        }

        for txn in transactions:
            analysis = txn.tax_analysis
            
            # Format Description
            desc = f"{txn.merchant_name} - {analysis.justification_text}".replace(";", "-").replace("\n", " ")
            
            # Value (Absolute)
            val = abs(float(txn.amount))
            
            # Determine Classification Code
            cat_key = analysis.category
            code = CATEGORY_MAP.get(cat_key, "P10.01.00012") 
            
            # Refine map based on Merchant/Description
            if code == "P10.01.00012":
                text = (str(txn.merchant_name) + " " + cat_key).lower()
                if "vivo" in text or "telefone" in text or "internet" in text: code = "P10.01.00007"
                elif "surya" in text or "dental" in text or "odonto" in text: code = "P10.01.00005"
                elif "sabesp" in text or "água" in text: code = "P10.01.00001"
                elif "cpfl" in text or "energia" in text or "luz" in text: code = "P10.01.00007"
                elif "aluguel" in text: code = "P10.01.00002"

            row = {
                "data": txn.date.strftime("%d/%m/%Y"),
                "codigo_plano_contas": code,
                "valor": val,
                "descrição": desc
            }
            data.append(row)

        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Sort by Date
        df["_sort_date"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        df = df.sort_values("_sort_date")
        df = df.drop(columns=["_sort_date"])
        
        # Convert to CSV in-memory
        stream = io.StringIO()
        df.to_csv(stream, index=False, encoding='utf-8-sig', sep=';', decimal=',')
        
        # Reset pointer
        stream.seek(0)
        
        # Prepare filename
        filename = f"tax_report_{month:02d}_{year}.csv"
        
        # Generator for streaming
        def iterfile():
            yield stream.getvalue()

        return StreamingResponse(
            iterfile(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
