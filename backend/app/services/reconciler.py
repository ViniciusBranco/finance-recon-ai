from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.models import Transaction, FinancialDocument
from thefuzz import fuzz
from datetime import timedelta

from sqlalchemy.orm import selectinload

class ReconciliationEngine:
    async def run_auto_reconciliation(self, session: AsyncSession) -> dict:
        results = {"matches_found": 0, "details": []}
        
        # 1. Fetch Candidates
        stmt_bank = select(Transaction).options(selectinload(Transaction.tax_analysis)).join(Transaction.document).where(
            FinancialDocument.doc_type == "BANK_STATEMENT",
            Transaction.receipt_id.is_(None)
        )
        bank_transactions = (await session.execute(stmt_bank)).scalars().all()
        
        stmt_receipts = select(Transaction).join(Transaction.document).where(
            FinancialDocument.doc_type == "RECEIPT"
        )
        receipt_transactions = (await session.execute(stmt_receipts)).scalars().all()
        
        # 2. Matching Logic with Dynamic Window
        for bank_txn in bank_transactions:
            best_match = None
            highest_score = 0.0
            
            for receipt_txn in receipt_transactions:
                # Rule 0: Exact Amount Match (Mandatory for deterministic link)
                if abs(bank_txn.amount) != abs(receipt_txn.amount):
                    continue
                
                # Pre-check: Dates must exist for auto-recon
                if bank_txn.date is None or receipt_txn.date is None:
                    continue

                # Rule 1: Dynamic Date Window (-1 to +5 days for bank clearing)
                # We subtract bank_txn.date from receipt_txn.date
                # Positive delta means statement is after receipt (standard)
                date_diff = (bank_txn.date - receipt_txn.date).days

                # Ajuste: Se for NF-e (DANFE), a janela de emissão pode ser de até 45 dias atrás
                # assumindo que o boleto foi gerado no faturamento e pago 30 dias depois.
                is_nfe = "NF-E" in receipt_txn.merchant_name or "DANFE" in receipt_txn.merchant_name
                max_window = 45 if is_nfe else 5
                
                # Window: Allow 1 day before (early clearing) and up to max_window days after (weekends/holidays/net30)
                if not (-1 <= date_diff <= max_window):
                    continue
                
                # Rule 2: Description Fuzzy Match
                # Compare bank description with merchant name from receipt
                name_score = fuzz.token_set_ratio(
                    bank_txn.merchant_name.lower(), 
                    receipt_txn.merchant_name.lower()
                ) / 100.0
                
                # Rule 3: Date Proximity Score
                # Closer dates get higher priority (e.g., diff 0 = 1.0, diff 5 = 0.5)
                proximity_score = 1.0 - (abs(date_diff) * 0.1)
                
                # Total Score Weighting
                final_score = (name_score * 0.7) + (proximity_score * 0.3)
                
                if final_score > highest_score and final_score > 0.6:
                    highest_score = final_score
                    best_match = receipt_txn
            
            # 3. Apply Best Match
            if best_match:
                bank_txn.receipt_id = best_match.document_id
                bank_txn.match_score = highest_score
                bank_txn.match_type = "AUTO_FUZZY"
                
                session.add(bank_txn)
                results["matches_found"] += 1
                results["details"].append({
                    "bank_txn_id": str(bank_txn.id),
                    "receipt_doc_id": str(best_match.document_id),
                    "score": highest_score,
                    "date_diff": (bank_txn.date - best_match.date).days
                })
        
        accuracy = results["matches_found"] / len(receipt_transactions) if receipt_transactions else 0.0
        results["reconciled_transactions"] = results["matches_found"]
        results["accuracy"] = accuracy
        
        await session.commit()
        return results