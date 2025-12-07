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
    """Parses CSV and prepares context for LLM if necessary."""
    try:
        df = pd.read_csv(state["file_path"])
        # Take first 5 rows to understand context
        content_preview = df.head(5).to_string()
        
        # For CSV, we pass the content to the LLM to understand if it's a statement or something else
        # Or we could extract deterministically if the format is known.
        # Following instructions: "CSV -> parse_csv -> structure_with_llm"
        # We'll store the content in a temporary way or update 'extracted_data' partially so LLM can pick it up?
        # The instruction says "structure_with_llm" uses "Analyze the following text".
        # So we'll put the CSV content into a 'raw_text' convention field or pass it via state context not defined in TypedDict yet?
        # The TypedDict definition in instructions didn't have 'raw_text', but 'extracted_data.raw_content' exists.
        # But 'structure_with_llm' expects text. Let's assume we can add 'raw_text' to the TypedDict or reuse 'error' (bad practice).
        # Better: let's stick to the schema provided in instructions.
        # But wait, instruction #2 said ProcessingState has `file_path`, `password`, `file_extension`, `extracted_data`, `error`.
        # It missed `raw_text`. I should probably have added `raw_text` to ProcessingState to facilitate data passing between nodes.
        # I'll implicitly assume the previous node returns it to be used by the next.
        # Let's return it as part of 'extracted_data' with raw_content populated, effectively acting as the carrier.
        
        doc = FinancialDocument(
            file_name=os.path.basename(state["file_path"]),
            doc_type="UNKNOWN", # LLM will decide
            raw_content=content_preview
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
workflow.add_edge("parse_csv", "extract_structured_data")

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
                                category="General"
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
                                category="Receipt"
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
