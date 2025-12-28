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
        # Bank Transactions: From Bank Statements, not yet linked
        stmt_bank = select(Transaction).options(selectinload(Transaction.tax_analysis)).join(Transaction.document).where(
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
        
        # Optimization: Loop through Bank Transactions to find their best Receipt match (supports N:1)
        
        for bank_txn in bank_transactions:
            candidates = []
            
            try:
                b_amt = float(bank_txn.amount)
            except:
                continue
                
            for receipt_txn in receipt_transactions:
                doc_id = receipt_txn.document_id
                
                try:
                    r_amt = float(receipt_txn.amount)
                except:
                    continue
                
                # --- Matching Logic ---
                
                match_type = "AUTO"
                installment_info = ""
                score_penalty = 0.0
                
                # Check 1. Value Match (Primary)
                # Absolute diff
                diff_1to1 = abs(abs(b_amt) - abs(r_amt))
                is_1to1 = diff_1to1 <= 0.05
                
                is_installment = False
                
                # Check 2. Installment Match (Fractional)
                # Only check if 1:1 failed
                if not is_1to1:
                    for n in range(2, 13):
                        target = abs(r_amt) / n
                        # Tolerance R$ 1.00 for rounding differences
                        if abs(abs(b_amt) - target) <= 1.0:
                            is_installment = True
                            installment_info = f"{n}"
                            match_type = "INSTALLMENT"
                            # Small penalty for installment to prefer direct matches if ambiguous
                            score_penalty = 0.05 
                            break
                
                if not is_1to1 and not is_installment:
                    continue
                
                # Check 3. Date Window (+/- 3 days)
                date_penalty = abs((bank_txn.date - receipt_txn.date).days)
                if date_penalty > 3:
                     # For installments, dates might be far apart (months later)
                     # But Requirements didn't specify relaxing date for installments, 
                     # except "Outcome: Re-run...". Installments usually obey due dates.
                     # If the Receipt Date (Emission) is Oct 10, and Installment 1 is Nov 10, diff is 30 days.
                     # The date filter currently uses "receipt_txn.date" which comes from the Document (Emission).
                     # If I enforce 3 days, Installments WILL FAIL if they are future dated.
                     
                     # Wait, usually `receipt_txn.date` is extracted as Issue Date.
                     # If we parsed Installments as separate transactions (Fix 2), their date is the Due Date.
                     # In that case, `receipt_txn.date` is Nov 14 (from previous Neodent example).
                     # So date match works.
                     # BUT for "Surya Dental" where we match "TOTAL NF (845,73)" (Issue Date check)
                     # The "Total NF" date is Issue Date.
                     # The Bank Transaction is likely the Payment Date.
                     # If it's the *first* installment, it might be close. If it's the 2nd, it's 30 days later.
                     
                     # User requirement 4: "Safety Trait: Installment matching must still strictly validate the Merchant Name..."
                     # User did NOT explicitly say "relax date".
                     # But logically, installments happen later.
                     # However, looking at the instruction: "matches a 281.91 receipt [Installment?]".
                     # "Ensure the Surya Dental installment (281,01) is automatically linked to the total NF (845,73)."
                     # If 845.73 has Issue Date = X.
                     # And simple parsing gave us that.
                     # Then Bank Txn has Date = X + 30 days.
                     # Current code `if date_penalty > 3: continue` will REJECT it.
                     
                     # I should PROBABLY relax date check for Installments?
                     # Or assume the user wants me to fix the logic described.
                     # "Task: Enhance ... to support 'Installment Matching'".
                     # If I don't relax date, most will fail.
                     # Let's verify strictness.
                     # "Safety Trait... must still strictly validate Merchant Name".
                     # This implies other things might be loose.
                     
                     if is_installment:
                         # Relax date for installments to e.g. 180 days?
                         if date_penalty > 180:
                             continue
                     else:
                         continue

                # Check 4. Name Similarity
                name_score = fuzz.partial_ratio(receipt_txn.merchant_name.lower(), bank_txn.merchant_name.lower())
                
                # Safety Trait: Strict name validation for Installments
                if is_installment and name_score < 85:
                    continue
                
                candidates.append({
                    "receipt_txn": receipt_txn,
                    "date_penalty": date_penalty,
                    "name_score": name_score,
                    "match_type": match_type,
                    "installment_n": installment_info,
                    "base_score_penalty": score_penalty
                })

            if not candidates:
                continue
            
            # Sort: Smallest Date Penalty -> Highest Name Score
            candidates.sort(key=lambda x: (x["date_penalty"], -x["name_score"]))
            best = candidates[0]
            
            # Final Score Calculation
            final_score = 0.9 - (best["date_penalty"] * 0.05) # Reduced penalty per day (0.05) to allow 1-2 weeks variance
            if is_installment and best["date_penalty"] > 5:
                 # Installments often have dates far from emission. 
                 # We shouldn't penalize too heavily if name is perfect.
                 # Let's cap penalty impact or adjust formula.
                 final_score = 0.85 # Baseline confidence for distant installment
            
            if best["name_score"] > 80:
                final_score += 0.1
            
            final_score -= best["base_score_penalty"]
            final_score = min(final_score, 1.0)
            
            # Threshold
            if final_score >= 0.70: # Slightly lower threshold to accept installments
                final_match = bank_txn
                doc_id = best["receipt_txn"].document_id
                
                final_match.receipt_id = doc_id
                final_match.match_score = final_score
                final_match.match_type = best["match_type"]
                # Store installment N? The model has no field for it.
                # User said "Include the installment number (N) in the internal metadata if possible".
                # Model doesn't have metadata yet. We skip or put in match_type? 
                # "match_type = 'INSTALLMENT'". 
                # I'll append to category or description? No, unsafe.
                # Just stick to match_type string as per instruction. 
                # Wait, "Include the installment number (N) in the internal metadata if possible".
                # I don't see a metadata column in Transaction model available in my view.
                # I will append to match_type: "INSTALLMENT (3)"? Column is String.
                if best["installment_n"]:
                     final_match.match_type = f"INSTALLMENT ({best['installment_n']})"
                
                session.add(final_match)
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
