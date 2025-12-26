import os
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from app.core.config import settings

# Define paths
# d:\Projects\vbti\finance-recon-ai\backend\app\core\tax_engine\ingest.py
# Go up 4 levels to get to backend root? 
# app/core/tax_engine -> backend/app/core/tax_engine
# __file__ dir is backend/app/core/tax_engine
# 1 up: backend/app/core
# 2 up: backend/app
# 3 up: backend
# 4 up: finance-recon-ai (Wait, user wants backend/knowledge)
# Backend root is 3 levels up from this file's directory.

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))
KNOWLEDGE_DIR = os.path.join(BACKEND_ROOT, "knowledge", "tax_rules")
VECTOR_STORE_DIR = os.path.join(BACKEND_ROOT, "knowledge", "vector_store")

def ingest_rules():
    if not os.path.exists(KNOWLEDGE_DIR):
        print(f"Error: Knowledge directory not found at {KNOWLEDGE_DIR}")
        return

    print(f"Loading PDFs from {KNOWLEDGE_DIR}...")
    # Use glob to find specific PDFs or match all
    loader = DirectoryLoader(KNOWLEDGE_DIR, glob="*.pdf", loader_cls=PyPDFLoader)
    documents = loader.load()
    print(f"Loaded {len(documents)} document pages.")

    if not documents:
        print("No documents found to ingest.")
        return

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks.")

    print("Initializing embeddings (nomic-embed-text)...")
    # Ensure OLLAMA_BASE_URL is correct. 
    # If users runs this as script, settings might need env vars loaded.
    # We rely on app.core.config to load .env
    
    embedding_model = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url=settings.OLLAMA_BASE_URL
    )

    print("Creating vector store...")
    vector_store = FAISS.from_documents(chunks, embedding_model)
    
    vector_store.save_local(VECTOR_STORE_DIR)
    print(f"Vector store saved to {VECTOR_STORE_DIR}")

if __name__ == "__main__":
    ingest_rules()
