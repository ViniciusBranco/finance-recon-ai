import re
from datetime import datetime
from .base import DocumentParser

class DanfeParser(DocumentParser):
    @classmethod
    def detect(cls, text: str) -> bool:
        return "DANFE" in text and "NOTA FISCAL" in text

    def extract(self, text: str) -> dict:
        result = {
            "doc_type": "RECEIPT",
            "date": None,
            "amount": None,
            "merchant_or_bank": None
        }

        # Date Extraction
        # Looking for DATA EMISSÃO followed by a date on a subsequent line
        # Snippet: "DATA EMISSÃO\nVinicius Branco Silva ... 29/11/2025"
        date_match = re.search(r"DATA EMISSÃO.*?\n.*?(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if date_match:
            try:
                date_str = date_match.group(1)
                dt = datetime.strptime(date_str, "%d/%m/%Y")
                result["date"] = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Amount Extraction
        # Look for "VALOR TOTAL DA NOTA"
        # The values line is usually the next one: "R$0,00 ... R$8,66"
        # We want the LAST monetary value in that line.
        amount_header_match = re.search(r"VALOR TOTAL DA NOTA", text, re.IGNORECASE)
        if amount_header_match:
            # Get the text after the match
            post_header = text[amount_header_match.end():]
            # Get the first non-empty line after header
            # Usually the next line contains the values
            lines = post_header.split('\n')
            for line in lines:
                if not line.strip():
                    continue
                
                # Find all R$ values
                matches = re.findall(r"R\$([\d\.,]+)", line)
                if matches:
                    # The last one is typically the total note value
                    raw_amount = matches[-1]
                    try:
                        clean_amount = raw_amount.replace('.', '').replace(',', '.')
                        result["amount"] = float(clean_amount)
                    except ValueError:
                        pass
                break

        # Merchant Extraction
        # Heuristic: The merchant name often appears early in the text, under "RECEBEMOS DE" or top lines.
        # Snippet: "RECEBEMOS DE AMAZON SERVICOS DE VAREJO DO BRASIL LTDA..."
        merchant_match = re.search(r"RECEBEMOS DE\s+(.+?)\s+OS PRODUTOS", text, re.IGNORECASE)
        if merchant_match:
            result["merchant_or_bank"] = merchant_match.group(1).strip()
        else:
            # Fallback: Look for "IDENTIFICAÇÃO DO EMITENTE" and take next line
            emitente_match = re.search(r"IDENTIFICAÇÃO DO EMITENTE.*?\n(.+?)\n", text, re.IGNORECASE | re.DOTALL)
            if emitente_match:
                # Sometimes "DANFE" is on the same line or next, might need cleanup
                candidate = emitente_match.group(1).strip()
                if "DANFE" not in candidate:
                    result["merchant_or_bank"] = candidate
                else:
                     # Try line after DANFE
                     lines = text.split('\n')
                     for i, line in enumerate(lines):
                         if "IDENTIFICAÇÃO DO EMITENTE" in line:
                             # Look ahead a few lines
                             for j in range(1, 4):
                                 if i+j < len(lines) and "DANFE" not in lines[i+j] and lines[i+j].strip():
                                     result["merchant_or_bank"] = lines[i+j].strip()
                                     break
                             break

        return result
