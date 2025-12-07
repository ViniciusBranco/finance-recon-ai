from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.models import Transaction, FinancialDocument
from thefuzz import fuzz
from datetime import timedelta

class ReconciliationEngine:
    async def run_auto_reconciliation(self, session: AsyncSession) -> dict:
        results = {"matches_found": 0, "details": []}
        
        # 1. Fetch Candidates
        # Bank Transactions: From Bank Statements, not yet linked
        stmt_bank = select(Transaction).join(Transaction.document).where(
            FinancialDocument.doc_type == "BANK_STATEMENT",
            Transaction.receipt_id.is_(None)
        )
        bank_transactions = (await session.execute(stmt_bank)).scalars().all()
        
        # Receipt Transactions: Representing the extracted data from Receipts
        # We use these to find the amounts/dates of the documents
        stmt_receipts = select(Transaction).join(Transaction.document).where(
            FinancialDocument.doc_type == "RECEIPT"
        )
        receipt_transactions = (await session.execute(stmt_receipts)).scalars().all()
        
        # Optimization: Build index or simple loop? N*M is fine for small count.
        # For larger datasets, we'd query per receipt or filter in DB.
        
        matched_bank_ids = set()
        
        for receipt_txn in receipt_transactions:
            # The document verifying this transaction
            doc_id = receipt_txn.document_id
            
            # Filter matches
            candidates = []
            for bank_txn in bank_transactions:
                if bank_txn.id in matched_bank_ids:
                    continue
                
                # Check Amount Tolerance (0.05)
                # Note: Transaction.amount is Decimal. receipt_txn.amount is Decimal.
                diff = abs(float(bank_txn.amount) - float(receipt_txn.amount))
                if diff > 0.05:
                    continue
                
                # Check Date Tolerance (+/- 3 days)
                # Transaction.date is datetime.date usually (from model 'Date')
                date_diff = abs((bank_txn.date - receipt_txn.date).days)
                if date_diff > 3:
                    continue
                
                # Calculate Score
                score = 0.8 # Base for Date+Amount
                
                # Merchant Fuzzy Match
                # e.g. "UBER * TRIP" vs "Uber"
                name_score = fuzz.partial_ratio(receipt_txn.merchant_name.lower(), bank_txn.merchant_name.lower())
                if name_score > 80:
                    score += 0.2
                
                candidates.append((score, bank_txn))
            
            # Decision
            if not candidates:
                continue
            
            # Sort by score desc
            candidates.sort(key=lambda x: x[0], reverse=True)
            
            best_score, best_match = candidates[0]
            
            # Thresholds
            # If strictly one > 0.8? Or just best > 0.8?
            # Instructions: 
            # "If exactly one candidate > 0.8 -> Link"
            # "If multiple -> Take highest if > 0.9"
            
            final_match = None
            
            high_scores = [c for c in candidates if c[0] > 0.8]
            
            if len(high_scores) == 1:
                final_match = high_scores[0][1]
            elif len(high_scores) > 1:
                # Multiple candidates, check if best is > 0.9
                if best_score > 0.9:
                    final_match = best_match
            
            if final_match:
                # Apply Link
                final_match.receipt_id = doc_id
                final_match.match_score = best_score
                final_match.match_type = "AUTO"
                
                session.add(final_match)
                matched_bank_ids.add(final_match.id)
                results["matches_found"] += 1
                results["details"].append({
                    "bank_txn_id": str(final_match.id),
                    "receipt_doc_id": str(doc_id),
                    "score": best_score
                })
        
        if bank_transactions:
            accuracy = results["matches_found"] / len(bank_transactions)
        else:
            accuracy = 0.0

        results["reconciled_transactions"] = results["matches_found"]
        results["accuracy"] = accuracy
        
        await session.commit()
        return results
