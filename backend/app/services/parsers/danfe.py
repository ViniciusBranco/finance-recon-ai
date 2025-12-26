import re
from datetime import datetime
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.config import settings
from app.schemas.document import FinancialDocument
from .base import DocumentParser

class DanfeParser(DocumentParser):
    def __init__(self):
        self.llm = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model="qwen2.5:7b",
            temperature=0.0, # Low temp for extraction
            format="json"
        )
        self.parser = JsonOutputParser(pydantic_object=FinancialDocument)
        
        # Refined Prompt for NFe Extraction (Fix 2)
        self.prompt = PromptTemplate(
            template="""Analyze the following text from a Brazilian NFe (Nota Fiscal Eletrônica/DANFE).
            
            **Goal**: Extract the Issue Date, Total Amount, and Merchant Name.

            **Extraction Rules:**
            1. **Date (Data de Emissão)**: 
               - Look for "DATA DA EMISSÃO", "DATA DE EMISSÃO", or "EMISSÃO" in the header blocks.
               - Typically near "NÚMERO", "SÉRIE", or "SAÍDA/ENTRADA".
               - Return format: ISO 8601 "YYYY-MM-DD".
            
            2. **Amount (Valor Total)**:
               - Priority: Look for "VALOR TOTAL DA NOTA" or "V. TOTAL DA NOTA" (often in "CÁLCULO DO IMPOSTO" box).
               - Fallback: Look for "VALOR TOTAL" or the last large monetary value in the summary.
               - Format: numeric (e.g., 1250.00). Handle "1.250,00" -> 1250.00.
            
            3. **Merchant**:
               - Use "IDENTIFICAÇÃO DO EMITENTE", "Nome / Razão Social", or the logo text at top left.
            
            **Return JSON ONLY:**
            {format_instructions}

            **Input Text:**
            {text}
            """,
            input_variables=["text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )
        self.chain = self.prompt | self.llm | self.parser

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

        # --- 1. Regex Extraction (Primary Strategy - Faster) ---
        
        # Date Extraction
        if not result["date"]:
            # Pattern: "DATA DA EMISSÃO" followed by date
            date_match = re.search(r"DATA.*?EMISSÃO.*?\n.*?(\d{2}[-/]\d{2}[-/]\d{4})", text, re.IGNORECASE)
            if not date_match:
                 # Pattern: Date near "SAÍDA" or just the first date in standard header position
                 date_match = re.search(r"(\d{2}/\d{2}/\d{4})", text) 
            
            if date_match:
                try:
                    date_str = date_match.group(1).replace('-', '/')
                    dt = datetime.strptime(date_str, "%d/%m/%Y")
                    result["date"] = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        # Amount Extraction
        if not result["amount"]:
             # Try finding "VALOR TOTAL DA NOTA" box
             amount_match = re.search(r"(?:VALOR TOTAL DA NOTA|V\. TOTAL DA NOTA|VALOR TOTAL).*?R\$\s*([\d\.]+,\d{2})", text, re.IGNORECASE | re.DOTALL)
             if not amount_match:
                  amount_match = re.search(r"(?:VALOR TOTAL DA NOTA|V\. TOTAL DA NOTA|VALOR TOTAL)\D*?(\d+[,.]\d{2})", text, re.IGNORECASE)
             
             if amount_match:
                 try:
                     raw = amount_match.group(1)
                     # Brazil format: 1.000,00 -> 1000.00
                     clean = raw.replace('.', '').replace(',', '.')
                     result["amount"] = float(clean)
                 except ValueError:
                     pass

        # Merchant Extraction
        if not result["merchant_or_bank"]:
            # "RECEBEMOS DE [MERCHANT] OS PRODUTOS"
            merchant_match = re.search(r"RECEBEMOS DE\s+(.+?)\s+OS PRODUTOS", text, re.IGNORECASE)
            if merchant_match:
                result["merchant_or_bank"] = merchant_match.group(1).strip()
            else:
                # "IDENTIFICAÇÃO DO EMITENTE" Box
                emitente_match = re.search(r"IDENTIFICAÇÃO DO EMITENTE.*?\n(.+?)\n", text, re.IGNORECASE | re.DOTALL)
                if emitente_match:
                     candidate = emitente_match.group(1).strip()
                     # specific filtering for DANFE literal which sometimes appears in this block
                     if "DANFE" not in candidate and "DOCUMENTO" not in candidate:
                        result["merchant_or_bank"] = candidate

        # --- 2. Fallback to LLM (If missing data) ---
        # Only call LLM if we are missing critical data
        if not result["date"] or not result["amount"] or not result["merchant_or_bank"]:
            try:
                print("DEBUG: Regex failed for some DANFE fields. Falling back to LLM.")
                llm_result = self.chain.invoke({"text": text})
                if llm_result:
                    if not result["date"]:
                        result["date"] = llm_result.get("date")
                    if not result["amount"]:
                        result["amount"] = llm_result.get("amount")
                    if not result["merchant_or_bank"]:
                        result["merchant_or_bank"] = llm_result.get("merchant_or_bank")
            except Exception as e:
                print(f"DEBUG: DANFE LLM Extraction failed: {e}")

        # --- 3. Installments Extraction (Fatura / Duplicata) ---
        if "FATURA" in text.upper() or "DUPLICATA" in text.upper():
            installments = []
            
            # Strategy A: Explicit "Venc" label (Surya / Standard)
            # Pattern: Venc. 09/11/2025 Valor R$ 281,91
            matches_labeled = re.findall(r"Venc\.?\s*(\d{2}/\d{2}/\d{4}).*?Valor.*?R\$\s*([\d\.,]+)", text, re.IGNORECASE | re.DOTALL)
            
            # Strategy B: Tabular (Neodent)
            # Pattern: 14.11.2025 ... 189,00 (appearing in FATURA block)
            matches_tabular = re.findall(r"\b(\d{2}[./]\d{2}[./]\d{4})\b\s+(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})\b", text)
            
            all_matches = []
            if matches_labeled:
                for m in matches_labeled:
                     all_matches.append((m[0], m[1], "Labeled"))
            
            # Use Tabular as well
            if matches_tabular:
                 for m in matches_tabular:
                      all_matches.append((m[0], m[1], "Tabular"))

            # Deduplicate by (Date, Amount)
            unique_txns = {}

            count = 1
            for d_date_raw, d_val_raw, source in all_matches:
                 try:
                    # Clean Val
                    clean_val = float(d_val_raw.replace('.', '').replace(',', '.'))
                    
                    # Clean Date
                    date_clean = d_date_raw.replace('.', '/')
                    dt_obj = datetime.strptime(date_clean, "%d/%m/%Y")
                    iso_date = dt_obj.strftime("%Y-%m-%d")
                    
                    key = (iso_date, clean_val)
                    if key in unique_txns:
                        continue
                    
                    unique_txns[key] = {
                        "date": iso_date,
                        "amount": clean_val,
                        "description": f"Fatura {count} - {(result.get('merchant_or_bank') or 'NFe')}",
                        "merchant_or_bank": result.get("merchant_or_bank"),
                        "currency": "BRL"
                    }
                    count += 1
                 except ValueError:
                    continue
            
            if unique_txns:
                result["transactions"] = list(unique_txns.values())


        # Fallback for Merchant
        if not result["merchant_or_bank"]:
            # Old logic
            merchant_match = re.search(r"RECEBEMOS DE\s+(.+?)\s+OS PRODUTOS", text, re.IGNORECASE)
            if merchant_match:
                result["merchant_or_bank"] = merchant_match.group(1).strip()
            else:
                emitente_match = re.search(r"IDENTIFICAÇÃO DO EMITENTE.*?\n(.+?)\n", text, re.IGNORECASE | re.DOTALL)
                if emitente_match:
                     candidate = emitente_match.group(1).strip()
                     if "DANFE" not in candidate:
                        result["merchant_or_bank"] = candidate

        return result
