
import asyncio
import os
import sys

# Append parent dir to sys.path to access app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import engine
from sqlalchemy import text

async def patch_schema():
    print("Patching database schema to add competence fields...")
    async with engine.begin() as conn:
        try:
            # Add columns to financial_documents
            await conn.execute(text("ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS competence_month INTEGER"))
            await conn.execute(text("ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS competence_year INTEGER"))
            
            # Add columns to transactions
            await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS competence_month INTEGER"))
            await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS competence_year INTEGER"))
            await conn.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_finalized BOOLEAN DEFAULT FALSE"))
            
            print("Schema patch applied successfully.")
        except Exception as e:
            print(f"Error applying patch: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(patch_schema())
