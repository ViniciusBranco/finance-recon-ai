import re
from datetime import datetime
from .base import DocumentParser

class XPParser(DocumentParser):
    @classmethod
    def detect(cls, text: str) -> bool:
        # Detects XP patterns. The instructions mention "Banco XP" AND "Fatura".
        # Based on the sample output, let's look for "XP" and "Fatura" or "Encargos da fatura".
        # The user context explicitly said: Checks if text contains "Banco XP" AND "Fatura".
        # Note: OCR might be messy, so we act robustly.
        return "xp" in text.lower() and "fatura" in text.lower()

    def extract(self, text: str) -> dict:
        # Defaults
        result = {
            "doc_type": "BANK_STATEMENT",
            "date": None,
            "amount": None,
            "merchant_or_bank": "Banco XP",
            "transactions": []
        }

        # 1. Header Extraction (Date & Total Amount)
        
        # Regex: Vencimento.*?(\d{2}/\d{2}/\d{4})
        date_match = re.search(r"Vencimento.*?(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE | re.DOTALL)
        if date_match:
            date_str = date_match.group(1)
            try:
                # Convert to YYYY-MM-DD
                dt = datetime.strptime(date_str, "%d/%m/%Y")
                result["date"] = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Amount Extraction
        amount_patterns = [
            r"Total desta fatura\s*(?:R\$)?\s*([\d\.,]+)",
            r"Valor Total\s*(?:R\$)?\s*([\d\.,]+)",
            r"Subtotal\s*(?:R\$)?\s*([\d\.,]+)", 
            r"Valor a pagar\s*(?:R\$)?\s*([\d\.,]+)"
        ]

        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1)
                try:
                    clean_amount = amount_str.replace('.', '').replace(',', '.')
                    result["amount"] = float(clean_amount)
                    break 
                except ValueError:
                    continue

        # 2. Transaction Extraction
        # Pattern for: 12/11/25 IFD*KITMIX CONFEITARIA 14,89 0,00
        # Group 1: Date (DD/MM/YY)
        # Group 2: Description (Greedy until amount)
        # Group 3: Amount (BRL)
        # Trailing part is USD amount (ignore)
        txn_pattern = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([\d\.,]+)\s+[\d\.,]+$")

        transactions = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            match = txn_pattern.match(line)
            if match:
                raw_date, desc, raw_amount = match.groups()
                
                # Parse Date: DD/MM/YY -> YYYY-MM-DD
                try:
                    # Assuming 21st century (20xx)
                    t_date = datetime.strptime(raw_date, "%d/%m/%y")
                    formatted_date = t_date.strftime("%Y-%m-%d")
                except ValueError:
                    continue # Skip invalid dates

                # Parse Amount: 1.200,50 -> 1200.50
                try:
                    clean_amt = raw_amount.replace('.', '').replace(',', '.')
                    txn_amount = float(clean_amt)
                except ValueError:
                    continue

                transactions.append({
                    "date": formatted_date,
                    "merchant_name": desc.strip(),
                    "amount": txn_amount,
                    "category": None 
                })
        
        result["transactions"] = transactions
        return result
