from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.models import Transaction, FinancialDocument
from thefuzz import fuzz
import re
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
        
        stmt_receipts = select(Transaction).options(selectinload(Transaction.document)).join(Transaction.document).where(
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
                
                # Clean Bank Description for better matching
                # Remove common banking prefixes that add noise
                clean_bank_desc = re.sub(r"(?i)(PAG\s*BOLETO|PIX\s*QRS|PIX\s*TRANSF|DOC/TED|TRANSF|COMPRA|PAGTO|ENVIO|PIX)", "", bank_txn.merchant_name).strip()
                
                name_score = fuzz.token_set_ratio(
                    clean_bank_desc.lower(), 
                    receipt_txn.merchant_name.lower()
                ) / 100.0
                
                # Rule 2.1: Numeric Identifier Check (Deep Metadata)
                # Check for shared long numeric sequences (identifiers)
                bank_digits = re.findall(r'(\d{6,})', re.sub(r'[\.\-\/\s]', '', bank_txn.merchant_name))
                receipt_digits = re.findall(r'(\d{6,})', re.sub(r'[\.\-\/\s]', '', receipt_txn.merchant_name))
                
                identifier_match = False
                if bank_digits and receipt_digits:
                    # Check intersection
                    if set(bank_digits) & set(receipt_digits):
                        identifier_match = True
                        name_score = max(name_score, 0.95) # Force high match score for ID match
                
                # Rule 2.2: Keyword Intersection Score (Semantic Fallback)
                # If fuzzy fail, check if meaningful tokens from bank desc appear in PDF raw text
                # e.g. "VIVO FIXO" (Bank) vs "0082... VIVO ... FIXO" (PDF)
                if name_score < 0.6 and receipt_txn.document and receipt_txn.document.raw_text:
                    # Clean words like "PAG", "BOLETO", "INT", small numbers
                    raw_bank = re.sub(r"(?i)(PAG|BOLETO|PIX|TRANSF|COMPRA|ENVIO|INT|DOC|TED|QRS|[\d]{1,2})", " ", bank_txn.merchant_name)
                    bank_tokens = [t for t in re.split(r'[\s\/\-\.]', raw_bank) if len(t) > 2]
                    
                    if bank_tokens:
                        hits = 0
                        doc_text = receipt_txn.document.raw_text.upper()
                        for token in bank_tokens:
                            if token.upper() in doc_text:
                                hits += 1
                        
                        keyword_score = hits / len(bank_tokens)
                        
                        # Special Case: DARF/GPS
                        if "DARF" in bank_txn.merchant_name.upper() and ("DARF" in doc_text or "RECEITA FEDERAL" in doc_text):
                             keyword_score = max(keyword_score, 1.0)
                        
                        if keyword_score > 0.75:
                             # Boost confidence if keywords match strongly
                             name_score = max(name_score, 0.90)

                # Rule 3: Date Proximity Score
                # Closer dates get higher priority (e.g., diff 0 = 1.0, diff 5 = 0.5)
                proximity_score = 1.0 - (abs(date_diff) * 0.1)
                
                # Total Score Weighting
                final_score = (name_score * 0.7) + (proximity_score * 0.3)
                
                if final_score > highest_score and final_score > 0.6:
                    highest_score = final_score
                    best_match = receipt_txn

            # AMBIGUITY CHECK:
            # If we found a match, check if there are other candidates with crucial similarities that make this risky.
            if best_match:
                # Count exact duplicates (same amount + same date) in the receipts list
                # This prevents auto-linking when user has two identical receipts (e.g. 2x R$100 on same day)
                ambiguous_count = 0
                for r in receipt_transactions:
                     if r.amount == best_match.amount and r.date == best_match.date:
                         ambiguous_count += 1
                
                if ambiguous_count > 1:
                    # Too risky. Let user decide manually.
                    best_match = None
            
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