import os
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
            raw_content="XML Parsed"
        )
        return {**state, "extracted_data": doc}
    except Exception as e:
        return {**state, "error": f"XML Parsing failed: {str(e)}"}

def parse_csv(state: ProcessingState) -> ProcessingState:
    """Parses CSV and extracts transactions directly using Pandas (Bypassing LLM)."""
    try:
        file_path = state["file_path"]
        df = None
        
        # 1. Detect Encoding & Separator
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        separators = [',', ';', '\t']
        
        for enc in encodings:
            try:
                # Try sniffing with python engine
                temp_df = pd.read_csv(file_path, sep=None, engine='python', encoding=enc, nrows=5)
                # If we have at least 1 column, it's a good start
                if len(temp_df.columns) > 0:
                    # Re-read full file
                    df = pd.read_csv(file_path, sep=None, engine='python', encoding=enc)
                    break
            except Exception:
                continue
                
        if df is None:
             # Fallback: specific common formatted tries
             for enc in encodings:
                 for sep in separators:
                     try:
                        df = pd.read_csv(file_path, sep=sep, encoding=enc)
                        if len(df.columns) > 1: # Heuristic
                            break
                     except:
                        continue
                 if df is not None: break
        
        if df is None:
            return {**state, "error": "CSV Parsing failed: Could not determine encoding/separator."}
            
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
            transactions=transactions
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
            raw_content=text_content
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

def extract_structured_data(state: ProcessingState) -> ProcessingState:
    """Uses Strategy Pattern to structure data from raw content."""
    if state.get("error"):
        return state
    
    current_doc = state.get("extracted_data")
    if not current_doc or not current_doc.raw_content:
        return {**state, "error": "No content to process."}
    
    raw_text = current_doc.raw_content

    try:
        # Use Factory to get the correct parser (XP, Generic, etc.)
        parser = ParserFactory.get_parser(raw_text)
        result = parser.extract(raw_text)
        
        # Merge result
        updated_doc = FinancialDocument(
            file_name=current_doc.file_name,
            doc_type=result.get("doc_type", "UNKNOWN"),
            date=result.get("date"),
            amount=result.get("amount"),
            merchant_or_bank=result.get("merchant_or_bank"),
            raw_content=current_doc.raw_content,
            transactions=result.get("transactions")
        )
        
        return {**state, "extracted_data": updated_doc}
    except Exception as e:
        return {**state, "error": f"Data extraction failed: {str(e)}"}

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
from datetime import datetime
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
                db_doc.status = "PROCESSED"
                if not expected_type:
                    db_doc.doc_type = extracted.doc_type
                else:
                     # Respect expected hint even if parser was unsure, unless parser is very sure
                     # For now simple trust
                     pass 
                
                db_doc.raw_text = extracted.raw_content
                # db_doc.metadata_blob = extracted.metadata # Removed if not matching model, check model first
                
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
                            
                            txn_date_obj = datetime.strptime(t_date, "%Y-%m-%d").date() if t_date else datetime.utcnow().date()
                            
                            new_txn = DBTransaction(
                                document_id=db_doc.id,
                                merchant_name=t_desc or "Unknown",
                                date=txn_date_obj,
                                amount=t_amount or 0.0,
                                category="General",
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
                         
                         txn_date_obj = datetime.strptime(t_date, "%Y-%m-%d").date() if t_date else datetime.utcnow().date()
                         
                         new_txn = DBTransaction(
                                document_id=db_doc.id,
                                merchant_name=t_desc,
                                date=txn_date_obj,
                                amount=t_amount,
                                category="Receipt",
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
