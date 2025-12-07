import os
import pdfplumber
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END
from app.schemas.receipt import ExtractionState, ReceiptData
from app.core.config import settings

# --- Nodes ---

def load_pdf(state: ExtractionState) -> ExtractionState:
    """Extracts raw text from a PDF file."""
    file_path = state["file_path"]
    try:
        text_content = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text_content += page.extract_text() or ""
        
        if not text_content:
            return {**state, "error": "No text extracted from PDF."}
            
        return {**state, "raw_text": text_content}
    except Exception as e:
        return {**state, "error": f"Failed to load PDF: {str(e)}"}

def extract_info(state: ExtractionState) -> ExtractionState:
    """Uses LLM to extract structured data from raw text."""
    if state.get("error"):
        return state

    raw_text = state.get("raw_text", "")
    
    # Initialize the LLM (ensure Ollama is running with qwen2.5:7b)
    llm = ChatOllama(
        base_url=settings.OLLAMA_BASE_URL,
        model="qwen2.5:7b",
        temperature=0,
        format="json"
    )

    parser = JsonOutputParser(pydantic_object=ReceiptData)

    prompt = PromptTemplate(
        template="""You are an expert in data extraction from Brazilian receipts (Notas Fiscais).
        Extract the following information from the receipt text provided below.
        
        - Merchant Name
        - Date (Convert to YYYY-MM-DD format. If in DD/MM/YYYY, convert it.)
        - Total Amount (Extract the numeric value, handling 'R$' symbol. Use '.' for decimal point.)
        - CNPJ (if available)
        - Category (Infer based on the merchant and items, e.g., Food, Transport, Shopping)

        Return ONLY a JSON object compatible with the following format:
        {format_instructions}

        Receipt Text:
        {text}
        """,
        input_variables=["text"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    chain = prompt | llm | parser

    try:
        result = chain.invoke({"text": raw_text})
        # Validate with Pydantic
        structured_data = ReceiptData(**result)
        return {**state, "structured_data": structured_data}
    except Exception as e:
        return {**state, "error": f"LLM Extraction failed: {str(e)}"}

# --- Graph Construction ---

workflow = StateGraph(ExtractionState)

workflow.add_node("load_pdf", load_pdf)
workflow.add_node("extract_info", extract_info)

workflow.set_entry_point("load_pdf")
workflow.add_edge("load_pdf", "extract_info")
workflow.add_edge("extract_info", END)

app = workflow.compile()

def process_receipt(file_path: str) -> dict:
    """
    Main entry point to process a receipt PDF.
    """
    initial_state = ExtractionState(
        file_path=file_path, 
        raw_text=None, 
        structured_data=None, 
        error=None
    )
    result = app.invoke(initial_state)
    return result
