import asyncio
import os
import sys

# Add backend to path (parent directory of scripts)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Transaction, TaxAnalysis
from app.services.tax_agent import tax_agent

async def main():
    print("Starting Tax Engine Warm-up Test...")
    async with AsyncSessionLocal() as session:
        # 1. Search for dummy transaction
        print("Searching for VIVO or SABESP transaction in DB...")
        stmt = select(Transaction).where(
            (Transaction.merchant_name.ilike("%VIVO%")) | 
            (Transaction.merchant_name.ilike("%SABESP%"))
        ).limit(1)
        
        result = await session.execute(stmt)
        txn = result.scalar_one_or_none()
        
        if not txn:
            print("No suitable transaction found (VIVO/SABESP). Skipping test.")
            return

        print(f"Found transaction: {txn.merchant_name} - {txn.amount} - ID: {txn.id}")
        
        # 2. Prepare Data
        transaction_data = {
            "id": str(txn.id),
            "description": txn.merchant_name,
            "amount": float(txn.amount),
            "date": txn.date.isoformat(),
            "category": txn.category or "Utilities"
        }
        
        # Simulate content based on the prompt's request for "raw text if available"
        receipt_content = "COMPROVANTE DE PAGAMENTO\nCONCESSIONARIA: VIVO / TELEFONICA\nVALOR: R$ 100,00\nDATA: 2025-11-10\nREFERENCIA: TELEFONE CONSULTORIO"
        if "SABESP" in txn.merchant_name.upper():
             receipt_content = "COMPROVANTE DE PAGAMENTO\nSABESP - CIA SANEAMENTO\nAGUA E ESGOTO\nVALOR: R$ 80,00\nENDERECO: RUA DO CONSULTORIO, 123"

        # 3. Call Agent
        print(f"Calling Tax Agent for {txn.merchant_name}...")
        try:
            analysis = await tax_agent.analyze_transaction(
                transaction_data=transaction_data, 
                receipt_content=receipt_content,
                db_session=session
            )
            
            print("\n--- TAX ANALYSIS RESULT (Object) ---")
            print(analysis.model_dump_json(indent=2))
            
            # 4. Validation
            print("\nVerifying persistence in Database...")
            stmt_verify = select(TaxAnalysis).where(TaxAnalysis.transaction_id == txn.id)
            verification = (await session.execute(stmt_verify)).scalar_one_or_none()
            
            if verification:
                print(f"SUCCESS: Record persisted with ID {verification.id}")
                print(f"DB Classification: {verification.classification}")
                print(f"DB Risk Level: {verification.risk_level}")
            else:
                 print("FAILURE: Record NOT found in DB.")

            # Check logic
            if analysis.classificacao == "Dedutível" and analysis.natureza == "custeio":
                 print("LOGIC CHECK: PASS (Deductible/Custeio)")
            else:
                 print(f"LOGIC CHECK: WARN (Got {analysis.classificacao} / {analysis.natureza})")
                 print("Expected: Dedutível / custeio")

        except ValueError as e:
            if "LLM echoed input" in str(e):
                print(f"\nCAUGHT EXPECTED ERROR (Hallucination Guard): {e}")
            else:
                print(f"\nVALUE ERROR: {e}")
        except Exception as e:
            print(f"\nUNEXPECTED ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
