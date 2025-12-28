import asyncio
import os
import sys
import uuid
import json
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.services.tax_agent import tax_agent, TaxExpertAgent, TaxAnalysisResult
from app.db.models import TaxAnalysis, Transaction

# Manually configure DB
DATABASE_URL = settings.DATABASE_URL
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def validate_gemini_cost():
    print("Starting Gemini Cost Validation...")

    # 1. Define Mock Transaction
    txn_id = uuid.uuid4()
    mock_txn = {
        "id": str(txn_id),
        "description": "API CALCULATION TEST",
        "category": "Software",
        "amount": 100.00,
        "date": "2025-12-28",
        "merchant_name": "Google Cloud"
    }

    # 2. Mock the Receipt Content
    receipt_content = "Receipt for API Usage"

    # 3. Create a Dummy Transaction in DB to respect Foreign Key constraints
    async with AsyncSessionLocal() as session:
        try:
            # Check if document exists or create simple one (skipping for this unit test if possible,
            # but FK constraints might require it. Let's create a dummy txn directly if possible).
            # We need a financial document first usually. 
            # Simplified: Just insert the Transaction if we can (Assuming Document ID is nullable? No, it's False).
            # To avoid complexities, let's just use the tax_agent logic mocking the part where it saves.
            
            # Actually, to verify PERSISTENCE, we need real DB records.
            # So let's find an EXISTING transaction and overwrite its analysis for this test.
            from sqlalchemy import select
            stmt = select(Transaction).limit(1)
            result = await session.execute(stmt)
            existing_txn = result.scalar_one_or_none()
            
            if not existing_txn:
                print("No transactions found in DB to attach analysis to. Please verify DB seeded.")
                return

            print(f"Using existing transaction ID: {existing_txn.id} for cost test.")
            mock_txn["id"] = str(existing_txn.id) # Use real ID

            # Clear existing analysis if any
            stmt_del = select(TaxAnalysis).where(TaxAnalysis.transaction_id == existing_txn.id)
            res = await session.execute(stmt_del)
            existing_analysis = res.scalar_one_or_none()
            if existing_analysis:
                await session.delete(existing_analysis)
                await session.commit()
                print("Cleared old tax analysis for this transaction.")

        except Exception as e:
            print(f"DB Setup Error: {e}")
            return

        # 4. Mock the LLM Response
        # We need to monkeypatch the rag_chain entirely because replacing a method on RunnableSequence 
        # is restricted by Pydantic/Slots protection.
        
        original_chain = tax_agent.rag_chain

        class MockChain:
            async def ainvoke(self, input_dict, **kwargs):
                print(">>> Mock LLM Called")
                return {
                    "answer": json.dumps({
                        "classificacao": "Dedutível",
                        "natureza": "custeio",
                        "categoria": "Software",
                        "mes_lancamento": "12/2025",
                        "valor_total": 100.00,
                        "checklist": ["Teste"],
                        "risco_glosa": "Baixo",
                        "comentario": "Teste de Custo Gemini",
                        "citacao_legal": None,
                        "confianca": 1.0
                    }),
                    "usage_metadata": {
                        "prompt_token_count": 1500,
                        "candidates_token_count": 500,
                        "total_token_count": 2000
                    }
                }
        
        # Monkeypatch the chain itself
        tax_agent.rag_chain = MockChain()
        
        # Force Provider to GEMINI (Monkeypatch settings?)
        # Settings is a Pydantic object, usually immutable or loaded from env.
        # We can try to modify os.environ but settings might be already loaded.
        # Ideally we patch settings.LLM_PROVIDER
        
        # NOTE: Since settings is imported in tax_agent, we need to patch IT there.
        # But we imported settings here from app.core.config. 
        # Python modules are singletons.
        settings.LLM_PROVIDER = "GEMINI"
        print(f"Forced LLM_PROVIDER to: {settings.LLM_PROVIDER}")

        # 5. Run Analyze
        print("Running analyze_transaction...")
        result = await tax_agent.analyze_transaction(mock_txn, receipt_content, session)
        
        # 6. Verify DB
        stmt = select(TaxAnalysis).where(TaxAnalysis.transaction_id == existing_txn.id)
        db_res = await session.execute(stmt)
        analysis_record = db_res.scalar_one_or_none()

        if analysis_record:
            print("Analysis Record Found!")
            print(f"Prompt Tokens: {analysis_record.prompt_tokens} (Expected 1500)")
            print(f"Completion Tokens: {analysis_record.completion_tokens} (Expected 500)")
            print(f"Estimated Cost: {analysis_record.estimated_cost}")
            
            # Cost Calculation:
            # Input: 1500 * (1.25 / 1000000) = 0.001875
            # Output: 500 * (5.00 / 1000000) = 0.0025
            # Total USD: 0.004375
            # Total BRL: 0.004375 * 5.85 = 0.02559375
            expected_cost_usd = 0.004375
            expected_cost_brl = 0.004375 * 5.85
            
            # Use small epsilon for float comparison
            if (analysis_record.prompt_tokens == 1500 and 
                abs(analysis_record.estimated_cost - expected_cost_usd) < 0.0001 and
                abs(analysis_record.estimated_cost_brl - expected_cost_brl) < 0.0001):
                print(f"COST VALIDATION PASSED (USD: {analysis_record.estimated_cost:.6f}, BRL: {analysis_record.estimated_cost_brl:.6f})")
                await session.commit() # PERSIST FOR AUDIT
            else:
                print(f"COST VALIDATION FAILED.")
                print(f"Expected USD: {expected_cost_usd}, Got: {analysis_record.estimated_cost}")
                print(f"Expected BRL: {expected_cost_brl}, Got: {analysis_record.estimated_cost_brl}")
        else:
            print("No analysis record persisted.")

        # Restore
        tax_agent.rag_chain = original_chain

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(validate_gemini_cost())
