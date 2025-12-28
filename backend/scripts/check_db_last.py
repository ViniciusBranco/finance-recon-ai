import asyncio
from sqlalchemy import select
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import AsyncSessionLocal
from app.db.models import TaxAnalysis

async def check():
    async with AsyncSessionLocal() as s:
        r = await s.execute(select(TaxAnalysis).order_by(TaxAnalysis.created_at.desc()).limit(1))
        a = r.scalars().first()
        if a:
            print(f"Model ID in DB: {a.model_version}")
            print(f"Cost: {a.estimated_cost_brl}")
        else:
            print("No records found.")

if __name__ == "__main__":
    asyncio.run(check())
