import asyncio
import argparse
import sys
import os
import pandas as pd
from sqlalchemy import select, extract
from sqlalchemy.orm import selectinload

# Ensure we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import AsyncSessionLocal
from app.db.models import TaxAnalysis, Transaction, FinancialDocument

async def generate_report(target_month: str):
    try:
        month_str, year_str = target_month.split('/')
        month = int(month_str)
        year = int(year_str)
    except ValueError:
        print("Invalid date format. Use MM/YYYY")
        sys.exit(1)

    # Define export directory relative to backend root
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'exports')
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"tax_report_{month:02d}_{year}.csv")

    print(f"Generating report for {target_month}...")

    async with AsyncSessionLocal() as session:
        # Query Transactions joined with TaxAnalysis
        # Filter by date and Classification
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
            print(f"No deductible transactions found for {target_month}.")
            return

        data = []
        total_deductible = 0.0
        total_cost_usd = 0.0
        total_cost_brl = 0.0

        # Category Map (Simple heuristic based on standard chart of accounts)
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
            
            # Format Description: Merchant + Justification
            desc = f"{txn.merchant_name} - {analysis.justification_text}".replace(";", "-").replace("\n", " ")
            
            # Value (Absolute for Expense)
            val = abs(float(txn.amount))
            total_deductible += val
            
            # Accumulate Token Costs
            if analysis.estimated_cost:
                total_cost_usd += analysis.estimated_cost
            if analysis.estimated_cost_brl:
                total_cost_brl += analysis.estimated_cost_brl
                
            # Determine Classification Code
            # Simple fuzzy lookup or direct map
            cat_key = analysis.category
            code = CATEGORY_MAP.get(cat_key, "P10.01.00012") # Default to Material de Escritório/Geral
            
            # Refine map based on partial string if direct miss
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
                "valor": val, # Will be formatted by pandas decimal arg
                "descrição": desc
            }
            data.append(row)

        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Sort by Date
        df["_sort_date"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        df = df.sort_values("_sort_date")
        df = df.drop(columns=["_sort_date"])
        
        # Export to CSV (Excel compatible: utf-8-sig, semicolon sep, comma decimal)
        df.to_csv(output_file, index=False, encoding='utf-8-sig', sep=';', decimal=',')
        
        print(f"\n[SUCCESS] Report generated: {output_file}")
        
        # Summary Log
        print("\n" + "=" * 50)
        print(f"LIVRO CAIXA SUMMARY: {target_month}")
        print("=" * 50)
        print(f"Total Transactions Processed: {len(transactions)}")
        print(f"Total Deductible Amount:    R$ {total_deductible:,.2f}")
        print("-" * 50)
        print(f"AI Operational Cost (USD):  $  {total_cost_usd:.6f}")
        print(f"AI Operational Cost (BRL):  R$ {total_cost_brl:.6f}")
        print("=" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Tax Report (Livro Caixa)")
    parser.add_argument("--month", type=str, required=True, help="Target month in MM/YYYY format")
    
    args = parser.parse_args()
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(generate_report(args.month))
