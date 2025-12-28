import asyncio
import uuid
from datetime import datetime
import sys
import os

# Ensure we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import AsyncSessionLocal
from app.db.models import FinancialDocument, Transaction

async def seed_data():
    async with AsyncSessionLocal() as session:
        # Create a Mock Document
        doc_id = uuid.uuid4()
        doc = FinancialDocument(
            id=doc_id,
            filename="mock_statement_dec_2025.pdf",
            doc_type="BANK_STATEMENT", 
            status="PROCESSED",
            created_at=datetime(2025, 12, 1)
        )
        session.add(doc)
        
        # Create a Mock Transaction
        txn_id = uuid.uuid4()
        txn = Transaction(
            id=txn_id,
            document_id=doc_id,
            merchant_name="Adobe Creative Cloud",
            date=datetime(2025, 12, 10),
            amount=100.00,
            category="Software"
        )
        session.add(txn)
        
        await session.commit()
        print(f"Seeded Document {doc_id} and Transaction {txn_id}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_data())
