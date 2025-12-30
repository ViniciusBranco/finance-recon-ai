import os
import re
import xml.etree.ElementTree as ET
import pandas as pd
import pdfplumber
import pypdf
from typing import Literal
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END
from app.schemas.document import ProcessingState, FinancialDocument
from app.core.config import settings

# --- Nodes ---

def detect_file_type(state: ProcessingState) -> ProcessingState:
    """Detects file extension to route processing."""
    _, ext = os.path.splitext(state["file_path"])
    return {**state, "file_extension": ext.lower()}

def parse_xml(state: ProcessingState) -> ProcessingState:
    """Parses XML (NFe) deterministically."""
    try:
        tree = ET.parse(state["file_path"])
        root = tree.getroot()
        
        # Namespaces are common in NFe, usually http://www.portalfiscal.inf.br/nfe
        # Simplified extraction logic assuming standard structure
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        # Try to find date (dhEmi)
        date_node = root.find('.//nfe:dhEmi', ns)
        date_str = date_node.text[:10] if date_node is not None and date_node.text else None
        
        # Try to find total amount (vNF)
        amount_node = root.find('.//nfe:vNF', ns)
        amount = float(amount_node.text) if amount_node is not None and amount_node.text else None
        
        # Try to find merchant name (emit/xNome)
        merchant_node = root.find('.//nfe:emit/nfe:xNome', ns)
        merchant = merchant_node.text if merchant_node is not None else None

        doc = FinancialDocument(
            file_name=os.path.basename(state["file_path"]),
            doc_type="RECEIPT", # NFe is typically a receipt
            date=date_str,
            amount=amount,
            merchant_or_bank=merchant,
            raw_content="XML Parsed",
            competence_month=state.get("month"),
            competence_year=state.get("year")
        )
        return {**state, "extracted_data": doc}
    except Exception as e:
        return {**state, "error": f"XML Parsing failed: {str(e)}"}

def parse_csv(state: ProcessingState) -> ProcessingState:
    """Parses CSV and extracts transactions directly using Pandas (Bypassing LLM)."""
    try:
        file_path = state["file_path"]
        df = None
        
        if df is None:
             # Force UTF-8-SIG as per instructions, try common separators
             # "ensure that all string extractions and CSV/PDF reads force utf-8"
             separators = [',', ';', '\t']
             for sep in separators:
                 try:
                    df = pd.read_csv(file_path, sep=sep, encoding='utf-8-sig') # Forced encoding
                    if len(df.columns) > 1:
                        break
                 except Exception:
                    continue
        
        if df is None:
             # Last ditch: try python engine with delimiter sniffing but forced encoding
             try:
                df = pd.read_csv(file_path, sep=None, engine='python', encoding='utf-8-sig')
             except:
                pass

        if df is None:
            return {**state, "error": "CSV Parsing failed: Could not read with UTF-8-SIG encoding."}
            
        # 2. Normalize Columns
        # Remove BOM artifacts explicitly if encoding didn't catch it
        df.columns = [str(c).lower().strip().replace('\ufeff', '') for c in df.columns]
        
        # 3. Flexible Mapping
        # Map: ['data', 'date'], ['valor', 'value', 'amount'], ['descrição', 'description', 'memo']
        col_map = {
            'date': ['data', 'date', 'dt'],
            'amount': ['valor', 'value', 'amount', 'amt'],
            'description': ['descrição', 'description', 'memo', 'historico', 'merchant', 'estabelecimento', 'loja']
        }
        
        found_cols = {}
        for target, aliases in col_map.items():
            for alias in aliases:
                if alias in df.columns:
                    found_cols[target] = alias
                    break
                    
        # Validade Critical Columns
        if not found_cols.get('date') or not found_cols.get('amount'):
             # If mapping failed, maybe it's headerless? 
             # For now, return error or fallback to basic 0,1,2 index if needed.
             # Instructions imply column mapping.
             # Let's try to be smart? No, strict to instructions "Look for...".
             return {**state, "error": f"CSV Invalid: Missing columns. Found: {list(df.columns)}"}
        
        # 4. Extract Transactions
        transactions = []
        for _, row in df.iterrows():
            try:
                # Date Parsing
                raw_date = row[found_cols['date']]
                dt_obj = pd.to_datetime(raw_date, dayfirst=True, errors='coerce')
                if pd.isna(dt_obj):
                    continue
                date_str = dt_obj.strftime("%Y-%m-%d")
                
                # Amount Parsing
                raw_amount = row[found_cols['amount']]
                if isinstance(raw_amount, str):
                    # Handle "R$ 1.000,00" -> 1000.00
                    # Handle "1,000.00" -> 1000.00
                    cln = raw_amount.replace('R$', '').replace(' ', '')
                    if ',' in cln and '.' in cln:
                        # Ambiguous? Assume Brazil: dot=thousand, comma=decimal
                        if cln.rfind(',') > cln.rfind('.'):
                            cln = cln.replace('.', '').replace(',', '.')
                    elif ',' in cln:
                         # Assume comma decimal
                         cln = cln.replace(',', '.')
                    amount = float(cln)
                else:
                    amount = float(raw_amount)
                
                # Description
                desc = "CSV Import"
                if 'description' in found_cols:
                    desc_val = row[found_cols['description']]
                    if pd.notna(desc_val):
                        desc = str(desc_val)
                
                transactions.append({
                    "date": date_str,
                    "amount": amount, 
                    "merchant_or_bank": desc,
                    "description": desc,
                    "currency": "BRL"
                })
            except Exception:
                continue

        # 5. Create Document
        doc = FinancialDocument(
            file_name=os.path.basename(file_path),
            doc_type="BANK_STATEMENT", # CSV is typically a statement
            raw_content="CSV Parsed via Pandas",
            transactions=transactions,
            competence_month=state.get("month"),
            competence_year=state.get("year")
        )
        
        return {**state, "extracted_data": doc}
        
    except Exception as e:
        return {**state, "error": f"CSV Parsing failed: {str(e)}"}

def extract_pdf_text(state: ProcessingState) -> ProcessingState:
    """Extracts text from PDF, handling passwords."""
    try:
        text_content = ""
        # Check encryption with pypdf first if needed, but pdfplumber also passes handling.
        # However, instructions explicitly mention "Attempt to open. If pypdf.errors.FileNotDecryptedError..."
        
        # Let's try opening with pdfplumber. It wraps pdfminer.
        # To handle passwords explicitly and robustly as requested:
        
        try:
            with pdfplumber.open(state["file_path"], password=state.get("password")) as pdf:
                for page in pdf.pages:
                    text_content += page.extract_text() or ""
        except Exception as e:
            # Check for password error legacy or strict pypdf check
            # Often it raises pdfminer.pdfdocument.PDFPasswordIncorrect or similar.
            # Interpreting "FileNotDecryptedError" implies we might want to check with pypdf first or catch the specific error.
            # Check for empty string representation of PDFPasswordIncorrect
            if "password" in str(e).lower() or "decrypted" in str(e).lower() or type(e).__name__ == 'PDFPasswordIncorrect':
                if not state.get("password"):
                    return {**state, "error": "PASSWORD_REQUIRED"}
                else:
                    return {**state, "error": f"Invalid Password: {str(e)}"}
            raise e

        if not text_content:
             return {**state, "error": "No text extracted from PDF."}

        # Structure intermediate result
        doc = FinancialDocument(
            file_name=os.path.basename(state["file_path"]),
            doc_type="UNKNOWN",
            raw_content=text_content,
            competence_month=state.get("month"),
            competence_year=state.get("year")
        )
        return {**state, "extracted_data": doc}

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"DEBUG: PDF Extraction Error: {e}")
        return {**state, "error": f"PDF Extraction failed: {str(e)}"}

# ... imports ...
from app.services.parsers.factory import ParserFactory

# ...

def _parse_itau_fast_track(text: str) -> dict | None:
    """
    Parser determinístico aprimorado para múltiplos layouts Itaú (Pix, Títulos, Transferências).
    """
    try:
        from datetime import datetime
        text_lower = text.lower()
        
        # 1. Validação de Assinatura (Expandida)
        keywords = ["itaú", "itau", "unibanco", "comprovante de transação", "comprovante de pix", "solicitação de transferência"]
        if not any(k in text_lower for k in keywords):
            return None

        data = {}
        
        # 2. Extração de Data
        # Padrão A: Explicit labels
        date_explicit = re.search(r"(?:data da transferência|data de pagamento|data)\s*[:\s]*(\d{2}/\d{2}/\d{4})", text_lower)
        if date_explicit:
             try:
                dt_obj = datetime.strptime(date_explicit.group(1), "%d/%m/%Y")
                data["date"] = dt_obj.strftime("%Y-%m-%d")
             except: pass
             
        if not data.get("date"):
            # Padrão B: DD/MM/YYYY dates generic
            date_num_match = re.search(r"(\d{2}/\d{2}/\d{4})", text_lower)
            if date_num_match:
                try:
                    dt_obj = datetime.strptime(date_num_match.group(1), "%d/%m/%Y")
                    data["date"] = dt_obj.strftime("%Y-%m-%d")
                except: pass
            else:
                # Padrão C: 05 nov de 2025
                months_map = {
                    'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04', 'mai': '05', 'jun': '06',
                    'jul': '07', 'ago': '08', 'set': '09', 'out': '10', 'nov': '11', 'dez': '12',
                    'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04', 'maio': '05', 'junho': '06',
                    'julho': '07', 'agosto': '08', 'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
                }
                date_ext_match = re.search(r"(\d{1,2})\s+([a-zç]+)\s+de\s+(\d{4})", text_lower)
                if date_ext_match:
                    day, month_ext, year = date_ext_match.groups()
                    mon_code = next((v for k, v in months_map.items() if month_ext.startswith(k)), None)
                    if mon_code:
                         data["date"] = f"{year}-{mon_code}-{day.zfill(2)}"

        # 3. Extração de Valor
        # Padrão A: Explicit labels
        amount_match = re.search(r"(?:valor da transferência|valor pago|valor total|valor)\s*[:\s]*r?\$?\s*([\d\.]+,\d{2})", text_lower)
        if not amount_match:
             # Padrão B: Generic R$
             amount_match = re.search(r"r\$\s*([\d\.]+,\d{2})", text_lower)
        
        if amount_match:
            try:
                val_str = amount_match.group(1).replace(".", "").replace(",", ".")
                data["amount"] = float(val_str)
            except: pass

        # 4. Extração de Favorecido (Enhanced)
        merchant_patterns = [
            r"(?:nome|raz[ãa]o\s*social)\s*d[oa]\s*benefici[áa]rio[:\s]+([^\n\r]+)",
            r"(?:favorecido|benefici[áa]rio|destino)[:\s]+([^\n\r]+)",
            r"para[\n\s]+([a-z0-9\s\.\*]+)" # PIX pattern capturing next line or same line
        ]
        
        merch_match = None
        for pat in merchant_patterns:
            merch_match = re.search(pat, text_lower, re.IGNORECASE)
            if merch_match: break
            
        if merch_match:
            raw_cand = merch_match.group(1).strip().upper()
            
            # Clean Masking (***.123.456-**)
            # We remove the asterisks and the dot/dash separators often associated with partial CPFs
            # Goal: Keep "ALIGN TECHNOLOGY" but remove "***.000.***"
            if "*" in raw_cand:
                # Remove blocks of masking
                raw_cand = re.sub(r'[\*\.]+\d{3}[\*\.]+', '', raw_cand)
                raw_cand = raw_cand.replace("*", "")
            
            # Clean CNPJ/CPF noise if explicit match
            clean_cand = re.split(r"CNPJ|CPF|\d{2}\.|CHAVE", raw_cand)[0].strip()
            clean_cand = re.sub(r'[\d\.\/-]{11,}', '', clean_cand) # Remove long generic numbers
            clean_cand = clean_cand.strip(" -:.,")
            
            if len(clean_cand) > 3:
                 data["merchant_or_bank"] = clean_cand

        # 5. Validação
        if data.get("date") and data.get("amount") is not None:
            if not data.get("merchant_or_bank"):
                data["merchant_or_bank"] = "COMPROVANTE ITAU"
            data["doc_type"] = "RECEIPT"
            data["transactions"] = None
            return data
            
    except Exception as e:
        print(f"DEBUG: Fast-Track Itaú Error: {e}")
    return None

def _extract_transactions_generic(text: str) -> dict | None:
    """Regex-based extraction for standard Bank Statements (Date Description Amount)."""
    transactions = []
    lines = text.split('\n')
    
    # Generic Pattern: Date (DD/MM/YYYY or DD/MM) ... Description ... Amount (X.XXX,XX)
    pattern = re.compile(r"(\d{2}/\d{2}(?:/\d{4})?)\s+(.*?)\s+([-\+]?[\d\.]+,\d{2}[DC]?)")
    
    from datetime import datetime
    today = datetime.now()
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        if "saldo" in line.lower() or "data" in line.lower():
            continue

        match = pattern.search(line)
        if match:
            date_str, desc, amount_str = match.groups()
            
            desc = desc.strip()
            if len(desc) < 3: continue 
            
            try:
                # Amount Parsing
                is_negative = False
                clean_amt_str = amount_str.upper()
                
                if clean_amt_str.endswith('D'):
                    is_negative = True
                    clean_amt_str = clean_amt_str[:-1].strip()
                elif clean_amt_str.endswith('C'):
                    is_negative = False
                    clean_amt_str = clean_amt_str[:-1].strip()
                
                if clean_amt_str.startswith('-'):
                    is_negative = True
                    clean_amt_str = clean_amt_str[1:].strip()
                
                val = float(clean_amt_str.replace('.', '').replace(',', '.'))
                
                if is_negative: val = -abs(val)
                else: val = abs(val) # Bank statement: usually abs value + D suffix = negative
                
                # Date Parsing
                if len(date_str) <= 5: # DD/MM
                    # Try to infer year from header if possible, else current year
                    dt_val = f"{today.year}-{date_str[3:5]}-{date_str[0:2]}"
                else:
                     dt_obj = datetime.strptime(date_str, "%d/%m/%Y")
                     dt_val = dt_obj.strftime("%Y-%m-%d")

                transactions.append({
                    "date": dt_val,
                    "description": desc,
                    "merchant_or_bank": desc,
                    "amount": val,
                    "currency": "BRL"
                })
            except Exception:
                continue

    if len(transactions) > 0:
        return {
            "doc_type": "BANK_STATEMENT",
            "transactions": transactions,
            "merchant_or_bank": "Bank Statement Import"
        }
    return None

def _parse_danfe_fast_track(text: str) -> dict | None:
    """Extração robusta de NF-e com Estratégia Multi-Anchor."""
    try:
        from datetime import datetime
        
        # 1. Normalize
        text_flat = re.sub(r'[\s\n\r\t]+', ' ', text).upper()
        digits_only = re.sub(r'\D', '', text)
        if not re.search(r'(\d{44})', digits_only): return None
        
        data = {
            "doc_type": "RECEIPT", 
            "merchant_or_bank": "NF-E DANFE",
            "amount": 0.0,
            "date": None
        }

        # 2. Date Strategy (Aggressive + Raw Text Fallback)
        
        # 2.1 Global Scan on Raw Text (first 2000 chars)
        raw_head = text[:2000]
        # Robust regex for DD/MM/YYYY
        all_dates_raw = re.findall(r"(\d{2}/\d{2}/\d{4})", raw_head)
        
        # Validation Filter: Remove dates that are clearly outliers (e.g. 0000) or probably birthdays/etc if strict
        # For now, just ensure valid datetime parsing
        valid_dates = []
        now_year = datetime.now().year
        for d_str in all_dates_raw:
             try:
                 d_obj = datetime.strptime(d_str, "%d/%m/%Y")
                 if 2000 <= d_obj.year <= now_year + 1:
                     valid_dates.append(d_str)
             except: pass

        priority_date = None
        
        # 2.2 Prioritized Context Check (Case Insensitive)
        # Expanded check for multiple redundant labels like ZL Dental PDF
        strong_signals = [
            (r"EMISS[ÃA]O", 100),
            (r"DATA\s*DA\s*EMISS[ÃA]O", 100),
            (r"DATA\s*DE\s*EMISS[ÃA]O", 100),
            (r"DATA\s*EMISS[ÃA]O", 100),
            (r"SA[ÍI]DA", 100),
            (r"PROTOCOLO", 150),
            (r"DATA\s*DO\s*PROTOCOLO", 150)
        ]
        
        for lbl, winsize in strong_signals:
            # Case insensitive search
            lbl_matches = re.finditer(lbl, raw_head, re.IGNORECASE)
            for lbl_match in lbl_matches:
                window = raw_head[lbl_match.end():lbl_match.end()+winsize]
                dt_match = re.search(r"(\d{2}/\d{2}/\d{4})", window)
                if dt_match:
                    d_candidate = dt_match.group(1)
                    # Filter logic
                    try:
                        d_obj = datetime.strptime(d_candidate, "%d/%m/%Y")
                        if 2000 <= d_obj.year <= now_year + 1:
                            priority_date = d_candidate
                            break
                    except: pass
            if priority_date:
                break
        
        if priority_date:
            try:
                data["date"] = datetime.strptime(priority_date, "%d/%m/%Y").strftime("%Y-%m-%d")
            except: pass
        
        # 2.3 Fallback to valid dates found
        if not data["date"] and valid_dates:
            # Prefer the first one found in raw order as header usually starts with date
            try:
                data["date"] = datetime.strptime(valid_dates[0], "%d/%m/%Y").strftime("%Y-%m-%d")
            except: pass
        
        # 3. Amount Strategy
        amount_strategies = [
            (r"VALOR\s*TOTAL\s*DA\s*(?:NOTA|NF)", 120),
            (r"VALOR\s*A\s*PAGAR", 100),
            (r"TOTAL\s*A\s*PAGAR", 100),
            (r"VALOR\s*LIQUIDO", 100)
        ]
        
        vals = []
        for pat, win_size in amount_strategies:
             match = re.search(pat, text_flat)
             if match:
                 window = text_flat[match.end():match.end()+win_size]
                 cur_matches = re.finditer(r"([\d\.]+,\d{2})", window)
                 for cm in cur_matches:
                     try:
                         val = float(cm.group(1).replace(".", "").replace(",", "."))
                         if val > 0: vals.append(val)
                     except: pass
        
        if vals:
             data["amount"] = max(vals)

        # Fallback: Largest value in document (Aggressive)
        if data["amount"] == 0.0:
             # Find all currency-like patterns
             avg_matches = re.findall(r"(?:R\$|VALOR)\s*([\d\.]+,\d{2})", text_flat) # Anchored
             if not avg_matches:
                 avg_matches = re.findall(r"(?<!\d)([\d\.]+,\d{2})", text_flat) # Unanchored (Riskier)
             
             all_vals = []
             for m in avg_matches:
                 try: 
                     v = float(m.replace(".", "").replace(",", "."))
                     if v > 0: all_vals.append(v)
                 except: pass
             
             if all_vals:
                 data["amount"] = max(all_vals)

        # 4. Merchant Extraction
        rec_match = re.search(r"RECEBEMOS\s*DE", text_flat)
        if rec_match:
             window = text_flat[rec_match.end() : rec_match.end() + 150]
             # Splitting using common delimiters in DANFE header
             clean = re.split(r"CNPJ|CPF|OS PRODUTOS|A QUANTIA|DATA", window)[0]
             # Strip CNPJ patterns (embedded)
             clean = re.sub(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', '', clean)
             # Strip isolated numbers
             clean = re.sub(r'[\d\.\/-]{10,}', '', clean)
             clean = clean.strip(" -:.,")
             if len(clean) > 3:
                 data["merchant_or_bank"] = clean

        # 5. Check Flags
        if data["amount"] == 0.0 or not data["date"]:
             if "CHECK DATA" not in data.get("merchant_or_bank", ""):
                  data["merchant_or_bank"] = (data.get("merchant_or_bank") or "NF-E") + " (CHECK DATA)"

        return data
    except Exception as e:
        print(f"DANFE Error: {e}")
        return None

def _parse_generic_receipt_fast_track(text: str) -> dict | None:
    """Fallback para recibos via Janela de Proximidade."""
    try:
        text_flat = re.sub(r'[\s\n\r\t]+', ' ', text).upper()
        data = {"doc_type": "RECEIPT"}
        
        # Data Window
        m_lbl = re.search(r"DATA\s*(?:DO)?\s*(?:PAGAMENTO|EMISSAO)|EMISSAO", text_flat)
        if m_lbl:
             window = text_flat[m_lbl.end() : m_lbl.end() + 40]
             m_dt = re.search(r"(\d{2}/\d{2}/\d{4})", window)
             if m_dt:
                 from datetime import datetime
                 data["date"] = datetime.strptime(m_dt.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
        
        if not data.get("date"):
             # Fallback global search
             m = re.search(r"(\d{2}/\d{2}/\d{4})", text_flat)
             if m:
                 from datetime import datetime
                 data["date"] = datetime.strptime(m.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")

        # Valor Window
        val_patterns = [r"VALOR\s*TOTAL", r"TOTAL\s*PAGAR", r"TOTAL", r"VALOR"]
        for vp in val_patterns:
            m_lbl = re.search(vp, text_flat)
            if m_lbl:
                window = text_flat[m_lbl.end() : m_lbl.end() + 40]
                m_val = re.search(r"([\d\.]+,\d{2})", window)
                if m_val:
                    data["amount"] = float(m_val.group(1).replace(".", "").replace(",", "."))
                    break
        
        if not data.get("amount"):
             # Fallback global search R$
             m = re.search(r"R\$\s*([\d\.]+,\d{2})", text_flat)
             if m:
                 data["amount"] = float(m.group(1).replace(".", "").replace(",", "."))

        if not data.get("merchant_or_bank") or len(data.get("merchant_or_bank", "")) < 3:
             # Fallback Recovery: Take first 4 significant tokens/lines as candidate
             # This helps with VIVO/TIM receipts where "VIVO" is in header but not labeled "Merchant"
             lines = text_flat.splitlines()[:4]
             candidate = " ".join([l.strip() for l in lines if len(l.strip()) > 2])
             candidate = re.sub(r'[\d\.\-\/]+', '', candidate) # Strip numbers
             candidate = candidate[:50].strip()
             if len(candidate) > 2:
                 data["merchant_or_bank"] = candidate
                 
        if data.get("date") and data.get("amount"):
            return data
        
        # 3. Numeric Extraction (Identifiers)
        # Extract sequences of 8+ digits, stripping dots/slashes/dashes
        # Used for substring matching in Reconciler
        raw_clean = re.sub(r'[\.\-\/\s]', '', text_flat)
        identifiers = re.findall(r'(\d{8,})', raw_clean)
        # Filter duplicates and valid length
        data["identifiers"] = list(set([idl for idl in identifiers if len(idl) >= 8 and len(idl) <= 48]))
        
        if data.get("date") and data.get("amount"):
            return data
    except: pass
    return None
    
def extract_structured_data(state: ProcessingState) -> ProcessingState:
    """Orquestrador de extração com estratégias especializadas e bloqueio de LLM."""
    if state.get("error"):
        return state
    
    current_doc = state.get("extracted_data")
    if not current_doc or not current_doc.raw_content:
        return {**state, "error": "No content to process."}
    
    raw_text = current_doc.raw_content
    exp_type = state.get("expected_type")
    
    print(f"DEBUG: Processing with Strategy: {exp_type}")
    
    method = "UNKNOWN"
    result = None

    if exp_type == "BANK_STATEMENT":
        result = _extract_transactions_generic(raw_text)
        if result: 
            method = "STATEMENT_REGEX"
            print(f"SUCCESS: Statement Parsed with {len(result['transactions'])} txns")
        else:
            return {**state, "error": f"Failed to parse bank statement table. Content: {raw_text[:50]}..."}
            
    elif exp_type == "RECEIPT":
        # Chain
        result = _parse_itau_fast_track(raw_text)
        if result: method = "RECEIPT_ITAU"
        
        if not result:
            result = _parse_danfe_fast_track(raw_text)
            if result: method = "RECEIPT_DANFE"
            
        if not result:
            result = _parse_generic_receipt_fast_track(raw_text)
            if result: method = "RECEIPT_GENERIC"
        
        if not result:
            return {**state, "error": f"Failed to parse receipt (Fast Track). Content: {raw_text[:50]}..."}
    
    else:
        # Auto-Detect Logic
        # 1. Try Strict Receipt Parsers first
        result = _parse_itau_fast_track(raw_text) or _parse_danfe_fast_track(raw_text)
        if result:
             method = "AUTO_DETECT_RECEIPT_STRICT"
        
        if not result:
             # 2. Heuristic: Is it a statement?
             # Count DD/MM Patterns
             date_count = len(re.findall(r"\d{2}/\d{2}", raw_text))
             if date_count > 2:
                 result = _extract_transactions_generic(raw_text)
                 if result: method = "AUTO_DETECT_STATEMENT"
        
        if not result:
             # 3. Try Generic Receipt Fallback
             result = _parse_generic_receipt_fast_track(raw_text)
             if result: method = "AUTO_DETECT_RECEIPT_GENERIC"
             
        if not result:
             return {**state, "error": f"Layout não suportado (IA bloqueada na ingestão). Content: {raw_text[:50]}..."}
    
    if not result:
         return {**state, "error": "Extraction returned empty result."}

    updated_doc = FinancialDocument(
        file_name=current_doc.file_name,
        doc_type=result.get("doc_type", "UNKNOWN"),
        date=result.get("date"),
        amount=result.get("amount"),
        merchant_or_bank=result.get("merchant_or_bank"),
        raw_content=current_doc.raw_content,
        transactions=result.get("transactions")
    )
    
    return {**state, "extracted_data": updated_doc, "ingestion_method": method}

# --- Routing Logic ---

def route_file(state: ProcessingState) -> Literal["parse_xml", "parse_csv", "extract_pdf_text", "END"]:
    ext = state["file_extension"]
    if ext == ".xml":
        return "parse_xml"
    elif ext == ".csv":
        return "parse_csv"
    elif ext == ".pdf":
        return "extract_pdf_text"
    else:
        return "END"

def route_after_extraction(state: ProcessingState) -> Literal["extract_structured_data", "END"]:
    if state.get("error"):
        return "END"
    # Content is ready for structured data extraction
    return "extract_structured_data"

# --- Graph Construction ---

workflow = StateGraph(ProcessingState)

workflow.add_node("detect_file_type", detect_file_type)
workflow.add_node("parse_xml", parse_xml)
workflow.add_node("parse_csv", parse_csv)
workflow.add_node("extract_pdf_text", extract_pdf_text)
workflow.add_node("extract_structured_data", extract_structured_data)

workflow.set_entry_point("detect_file_type")

workflow.add_conditional_edges(
    "detect_file_type",
    route_file,
    {
        "parse_xml": "parse_xml",
        "parse_csv": "parse_csv",
        "extract_pdf_text": "extract_pdf_text",
        "END": END
    }
)

# XML ends after parsing
workflow.add_edge("parse_xml", END)

# CSV goes to extraction
workflow.add_edge("parse_csv", END)

# PDF goes to extraction if successful
workflow.add_conditional_edges(
    "extract_pdf_text",
    route_after_extraction,
    {
        "extract_structured_data": "extract_structured_data",
        "END": END
    }
)

workflow.add_edge("extract_structured_data", END)

import uuid
from datetime import datetime, date
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import FinancialDocument as DBFinancialDocument, Transaction as DBTransaction

app_processor = workflow.compile()


async def process_document(file_path: str, password: str = None, file_hash: str = None, original_filename: str = "unknown.pdf", expected_type: str = None) -> dict:
    """
    Main entry point to process a financial document.
    Persists initial state and updates with results.
    """
    # 1. Create DB Entry (PENDING)
    async with AsyncSessionLocal() as session:
        new_doc = DBFinancialDocument(
            filename=os.path.basename(file_path),
            original_filename=original_filename,
            file_hash=file_hash,
            doc_type=expected_type if expected_type else "UNKNOWN",
            status="PENDING"
        )
        session.add(new_doc)
        await session.commit()
        await session.refresh(new_doc)
        doc_id = new_doc.id

    initial_state = ProcessingState(
        file_path=file_path,
        password=password,
        file_extension="",
        expected_type=expected_type,
        ingestion_method=None,
        ingestion_logs=None,
        extracted_data=None,
        error=None
    )

    # 2. Run LangGraph (Async)
    try:
        result = await app_processor.ainvoke(initial_state)
    except Exception as e:
         # Fallback error handling if graph crashes
         async with AsyncSessionLocal() as session:
            stmt = select(DBFinancialDocument).where(DBFinancialDocument.id == doc_id)
            db_doc = (await session.execute(stmt)).scalar_one_or_none()
            if db_doc:
                db_doc.status = "ERROR"
                db_doc.raw_text = str(e)
                await session.commit()
         return {**initial_state, "error": str(e)}

    # 3. Update DB Entry
    extracted = result.get("extracted_data")
    error = result.get("error")

    async with AsyncSessionLocal() as session:
        stmt = select(DBFinancialDocument).where(DBFinancialDocument.id == doc_id)
        db_doc = (await session.execute(stmt)).scalar_one_or_none()
        
        if db_doc:
            if error:
                # If Password is required, delete the document so user can retry uploading with password
                # without hitting duplicate error (since file_hash would be same).
                if error == "PASSWORD_REQUIRED" or "Invalid Password" in str(error):
                    await session.delete(db_doc)
                    await session.commit()
                    # Return result as is, frontend will handle the prompt
                    return {**result, "doc_id": doc_id, "error": error}

                db_doc.status = "ERROR"
                db_doc.raw_text = error
            elif extracted:
                # Determine Status based on Quality
                doc_status = "PROCESSED"
                if getattr(extracted, "amount", 0.0) == 0.0 and getattr(extracted, "date", None) is None:
                    # STRICT: Only flag if BOTH signals failed.
                    doc_status = "REQUIRES_REVIEW"
                
                db_doc.status = doc_status

                if not expected_type:
                    db_doc.doc_type = extracted.doc_type
                else:
                     # Respect expected hint even if parser was unsure, unless parser is very sure
                     # For now simple trust
                     pass 
                
                db_doc.raw_text = extracted.raw_content
                
                # Telemetry
                db_doc.ingestion_method = result.get("ingestion_method")
                db_doc.ingestion_logs = result.get("ingestion_logs")
                
                # Competence (from User Input)
                db_doc.competence_month = getattr(extracted, 'competence_month', None)
                db_doc.competence_year = getattr(extracted, 'competence_year', None)
                
                # Save Transactions
                if extracted.transactions:
                    # Logic for Bank Statements with multiple transactions
                    for txn in extracted.transactions:
                        try:
                            # txn is expected to be a Pydantic object Transaction or dict depending on node
                            # The node extract_structured_data returns FinancialDocument pydantic object which has transactions as list of Transaction
                            
                            # Safely handle if it's dict or object
                            t_date = getattr(txn, 'date', None) or txn.get('date')
                            t_amount = getattr(txn, 'amount', None) or txn.get('amount')
                            
                            t_desc = (
                                getattr(txn, 'description', None) or 
                                getattr(txn, 'merchant_name', None) or
                                getattr(txn, 'merchant_or_bank', None) or
                                txn.get('description') or 
                                txn.get('merchant_name') or
                                txn.get('merchant_or_bank')
                            )
                            
                            t_curr = getattr(txn, 'currency', None) or txn.get('currency')
                            
                            txn_date_obj = datetime.strptime(str(t_date), "%Y-%m-%d").date() if t_date else datetime.utcnow().date()
                            
                            final_desc = t_desc or "Unknown"
                            # Append identifiers if present to aid reconciliation
                            if getattr(extracted, "identifiers", None):
                                # Take top 2 identifiers to avoid clutter
                                ids_str = " ".join(extracted.identifiers[:2])
                                final_desc = f"{final_desc} {ids_str}"

                            new_txn = DBTransaction(
                                document_id=db_doc.id,
                                merchant_name=final_desc,
                                date=txn_date_obj,
                                amount=t_amount or 0.0,
                                category="General",
                                # Competence
                                competence_month=db_doc.competence_month,
                                competence_year=db_doc.competence_year,
                                is_finalized=False,
                                # Reset Match State
                                receipt_id=None,
                                match_score=None,
                                match_type=None
                            )
                            session.add(new_txn)
                        except Exception:
                            continue # Skip bad lines

                elif extracted.doc_type == "RECEIPT":
                    # Logic for Single Receipt - typically extraction puts it in .amount, .date of FinancialDocument or Single Transaction?
                    # The prompt implies 1 receipt = 1 transaction usually, or just document metadata.
                    # Let's support creating a transaction for the receipt itself if amount is present
                    if extracted.amount is not None:
                         t_date = extracted.date
                         t_amount = extracted.amount
                         t_desc = extracted.merchant_or_bank or "Receipt"
                         
                         txn_date_obj = None
                         if t_date:
                             if isinstance(t_date, (datetime, date)):
                                 txn_date_obj = t_date if isinstance(t_date, date) else t_date.date()
                             else:
                                 try: txn_date_obj = datetime.strptime(str(t_date), "%Y-%m-%d").date()
                                 except: pass
                         
                         final_desc = t_desc
                         if getattr(extracted, "identifiers", None):
                             ids_str = " ".join(extracted.identifiers[:2])
                             final_desc = f"{final_desc} {ids_str}"
                         
                         new_txn = DBTransaction(
                                document_id=db_doc.id,
                                merchant_name=final_desc,
                                date=txn_date_obj,
                                amount=t_amount,
                                category="Receipt",
                                # Competence
                                competence_month=db_doc.competence_month,
                                competence_year=db_doc.competence_year,
                                is_finalized=False,
                                # Reset Match State
                                receipt_id=None,
                                match_score=None,
                                match_type=None
                         )
                         session.add(new_txn)
            
            await session.commit()
            
    # Return structure expected by API
    tx_count = 0
    if extracted and extracted.transactions:
        tx_count = len(extracted.transactions)
    elif extracted and extracted.doc_type == 'RECEIPT':
        tx_count = 1
        
    return {**result, "doc_id": str(doc_id), "transactions_extracted": tx_count}
