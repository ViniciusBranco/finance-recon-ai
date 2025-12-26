import re
from datetime import datetime
from typing import List, Optional
from .base import DocumentParser

class ItauParser(DocumentParser):
    @classmethod
    def detect(cls, text: str) -> bool:
        # Detect typical Itaú Personnalité keywords
        # Broader check: "Itaú" AND ("Extrato" or "Lançamentos" or "agência")
        return "Itaú" in text and ("extrato" in text.lower() or "lançamentos" in text.lower() or "agência" in text.lower())

    def extract(self, text: str) -> dict:
        transactions = []
        lines = text.split('\n')
        
        # State variables for "Stateful Row Reconstructor"
        current_date_str = None
        pending_date = None
        
        # Regex patterns
        # Date: dd/mm or dd/mm/yyyy
        # Itaú statements often have dd/mm at the start of the line
        date_pattern = re.compile(r'^(\d{2}/\d{2})(?:/\d{4})?')
        
        # Value: 1.234,56 or 123,45 (End of line usually, maybe with negative sign)
        # Regex to capture optional leading minus, amount, optional trailing minus
        # We ensure amount doesn't start with space.
        amount_pattern = re.compile(r'(?P<sign1>-)?\s*(?P<amt>[\d\.]+,\d{2})\s*(?P<sign2>-)?$')

        # Noise filters
        noise_terms = ["SALDO ANTERIOR", "SALDO TOTAL DO DIA", "SALDO TOTAL DISPONÍVEL", "REND PAGO APLIC", "SALDO PROVISORIO"]

        # Attempt to find year in the first few lines
        header_text = "\n".join(lines[:20])
        year_match = re.search(r'/(\d{4})', header_text)
        if year_match:
             current_year = int(year_match.group(1))
        else:
             current_year = datetime.now().year

        pending_desc = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Clean noise
            upper_line = line.upper()
            if any(noise in upper_line for noise in noise_terms):
                continue
            
            # 1. Check for Date at start
            date_match = date_pattern.match(line)
            
            if date_match:
                # We found a line starting with a date
                # Format: "25/11 LIS ITAU ..." or just "25/11"
                found_date_str = date_match.group(1) # dd/mm
                
                # Check if it has value
                amt_match = amount_pattern.search(line)
                
                if amt_match:
                    # Line has both Date and Value -> Complete Transaction
                    raw_val = amt_match.group("amt")
                    is_neg = (amt_match.group("sign1") == '-') or (amt_match.group("sign2") == '-')
                    
                    category = "General"
                    desc = line[date_match.end():amt_match.start()].strip()
                    
                    self._add_transaction(transactions, found_date_str, current_year, raw_val, is_neg, desc)
                    pending_date = None # Reset pending
                    pending_desc = ""
                else:
                    # Line has date but no value -> Partial (Header for txn?)
                    pending_date = found_date_str
                    # Check if there's a description
                    rem = line[date_match.end():].strip()
                    pending_desc = rem # Store for next line match
            
            elif pending_date:
                # We have a pending date from previous line, check if this line has value
                amt_match = amount_pattern.search(line)
                if amt_match:
                     raw_val = amt_match.group("amt")
                     is_neg = (amt_match.group("sign1") == '-') or (amt_match.group("sign2") == '-')
                     
                     # Description is the whole line up to amount?
                     desc_part = line[:amt_match.start()].strip()
                     
                     full_desc = f"{pending_desc} {desc_part}".strip()
                     if not full_desc:
                         full_desc = "Transaction Found"
                     
                     self._add_transaction(transactions, pending_date, current_year, raw_val, is_neg, full_desc)
                     pending_date = None
                     pending_desc = ""
                else:
                    # Still no value? Maybe description continued?
                    # Be careful not to merge infinite lines.
                    # For now, if no value found, ignore or treat as desc part?
                    # Itaú vertical layout: Date left, Value right.
                    pass

        return {
            "doc_type": "BANK_STATEMENT",
            "transactions": transactions,
            "merchant_or_bank": "Itaú Personnalité",
            "raw_content": text
        }

    def _add_transaction(self, transactions, date_str, year, raw_amt, is_neg, desc):
        try:
            # Parse Amount
            # 1.000,00 -> 1000.00
            val_float = float(raw_amt.replace('.', '').replace(',', '.'))
            if is_neg:
                val_float = -val_float
            
            # Parse Date
            # date_str is dd/mm
            dt = datetime.strptime(f"{date_str}/{year}", "%d/%m/%Y").date()
            final_date_str = dt.strftime("%Y-%m-%d")

            transactions.append({
                "date": final_date_str,
                "amount": val_float,
                "description": desc,
                "merchant_or_bank": "Itaú Personnalité",
                "currency": "BRL"
            })
        except Exception as e:
            pass
