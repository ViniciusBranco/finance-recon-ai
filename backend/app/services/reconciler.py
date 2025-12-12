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
            # Filter matches
            candidates = []
            for bank_txn in bank_transactions:
                if bank_txn.id in matched_bank_ids:
                    continue
                
                # 1. Value Match (Primary Filter)
                # Check Amount Tolerance (0.05)
                try:
                    b_amt = float(bank_txn.amount)
                    r_amt = float(receipt_txn.amount)
                except:
                    continue
                    
                diff = abs(b_amt - r_amt)
                if diff > 0.05:
                    continue
                
                # 2. Date Window Filter (+/- 3 days)
                # Calculate Date Penalty
                date_penalty = abs((bank_txn.date - receipt_txn.date).days)
                if date_penalty > 3:
                    continue
                
                # 3. Name Similarity (Secondary Signal)
                name_score = fuzz.partial_ratio(receipt_txn.merchant_name.lower(), bank_txn.merchant_name.lower())
                
                candidates.append({
                    "txn": bank_txn,
                    "date_penalty": date_penalty,
                    "name_score": name_score
                })
            
            # Decision Logic
            if not candidates:
                continue
            
            # Weighted Scoring / Priority
            # Priority 1: Smallest Date Penalty (date_penalty ASC)
            # Priority 2: Highest Name Score (name_score DESC)
            candidates.sort(key=lambda x: (x["date_penalty"], -x["name_score"]))
            
            best = candidates[0]
            
            # Determine Final Score for record
            # Base logic: Exact Date + Value = Very High Confidence
            # Formula: 1.0 matching value (implicit)
            # Penalty: -0.1 per day difference
            # Bonus: +0.1 if name matches well (>80)
            
            final_score = 0.9 - (best["date_penalty"] * 0.1)
            if best["name_score"] > 80:
                final_score += 0.1
                
            # Clamp to 1.0
            final_score = min(final_score, 1.0)
            
            # Threshold for Auto-Link
            # If date is exact (penalty 0), score is >= 0.9 -> Match
            # If date is off by 1 day (penalty 1), score is 0.8 -> Match
            # If date is off by 3 days (penalty 3), score is 0.6 -> Maybe not auto match unless name is good? -> 0.7
            
            if final_score >= 0.75:
                final_match = best["txn"]
                
                # Apply Link
                final_match.receipt_id = doc_id
                final_match.match_score = final_score
                final_match.match_type = "AUTO"
                
                session.add(final_match)
                matched_bank_ids.add(final_match.id)
                results["matches_found"] += 1
                results["details"].append({
                    "bank_txn_id": str(final_match.id),
                    "receipt_doc_id": str(doc_id),
                    "score": final_score
                })
        
        if receipt_transactions:
            accuracy = results["matches_found"] / len(receipt_transactions)
        else:
            accuracy = 0.0

        results["reconciled_transactions"] = results["matches_found"]
        results["accuracy"] = accuracy
        
        await session.commit()
        return results
