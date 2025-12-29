import asyncio
import sys
import os
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from tabulate import tabulate # Assuming installed or simple print

# Adjust path to enable imports from app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import AsyncSessionLocal
from app.db.models import FinancialDocument

async def audit_ingestion():
    async with AsyncSessionLocal() as session:
        stmt = select(FinancialDocument).order_by(FinancialDocument.created_at.desc()).limit(50)
        result = await session.execute(stmt)
        docs = result.scalars().all()
        
        table_data = []
        for doc in docs:
            method = doc.ingestion_method or "N/A"
            status = doc.status
            reason = ""
            
            if method == "LLM_FALLBACK" or method == "N/A":
                logs = doc.ingestion_logs
                if logs and logs.get("fast_track"):
                    ft_logs = logs["fast_track"]
                    res = ft_logs.get("result")
                    missing = ft_logs.get("missing", [])
                    reason = f"{res}: {missing}"
            
            table_data.append([
                doc.filename,
                doc.doc_type,
                method,
                status,
                reason
            ])
            
        print("\n=== Ingestion Audit Trail (Last 50) ===\n")
        try:
            from tabulate import tabulate
            print(tabulate(table_data, headers=["Filename", "Type", "Method", "Status", "Reason for Fallback"], tablefmt="grid"))
        except ImportError:
            # Fallback simple print
            print(f"{'Filename':<30} | {'Method':<15} | {'Status':<10} | {'Reason'}")
            print("-" * 80)
            for row in table_data:
                print(f"{row[0]:<30} | {row[2]:<15} | {row[3]:<10} | {row[4]}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(audit_ingestion())
