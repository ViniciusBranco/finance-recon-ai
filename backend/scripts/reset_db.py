import asyncio
import argparse
import sys
import os
from sqlalchemy import delete, update, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import AsyncSessionLocal
from app.db.models import TaxAnalysis, Transaction, FinancialDocument

async def reset_db(target_month: str = None, reset_all: bool = False, delete_docs: bool = False, force: bool = False):
    """
    Resets database records based on criteria.
    """
    
    # Confirmation prompt
    if not force:
        print("WARNING: This operation is destructive.")
        if reset_all:
            print("Target: ALL DATA (Tax Analyses, Transactions, Documents)")
        elif target_month:
            print(f"Target: Month {target_month} (Tax Analyses, Reconciliations)")
            if delete_docs:
                print("        + Documents uploaded in this month")
        
        confirm = input("Are you sure? (Type 'yes' to proceed): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

    async with AsyncSessionLocal() as session:
        async with session.begin(): # Start transaction
            try:
                if reset_all:
                    print("Deleting all Tax Analyses...")
                    await session.execute(delete(TaxAnalysis))
                    
                    print("Deleting all Transactions...")
                    await session.execute(delete(Transaction))
                    
                    print("Deleting all Financial Documents...")
                    await session.execute(delete(FinancialDocument))
                    
                    print("Full reset complete.")
                
                elif target_month:
                    try:
                        month_str, year_str = target_month.split('/')
                        month = int(month_str)
                        year = int(year_str)
                    except ValueError:
                        print("Invalid date format. Use MM/YYYY")
                        return

                    print(f"Processing for {month:02d}/{year}...")

                    # 1. Delete associated TaxAnalysis
                    # We need to find transactions in this month first
                    # Using subquery or join for delete is dialect specific, but for PG it works with specific syntax or just use WHERE IN
                    
                    # Identify Transaction IDs for the month
                    stmt_txns = select(Transaction.id).where(
                        extract('month', Transaction.date) == month,
                        extract('year', Transaction.date) == year
                    )
                    
                    # Delete Tax Analysis where transaction_id in stmt_txns
                    print("Deleting specific Tax Analyses...")
                    stmt_del_tax = delete(TaxAnalysis).where(
                        TaxAnalysis.transaction_id.in_(stmt_txns)
                    )
                    result_tax = await session.execute(stmt_del_tax)
                    print(f"Deleted {result_tax.rowcount} TaxAnalysis records.")

                    # 2. Reset Transaction reconciliation fields
                    print("Unlinking Reconciliations...")
                    stmt_update = update(Transaction).where(
                        extract('month', Transaction.date) == month,
                        extract('year', Transaction.date) == year
                    ).values(
                        receipt_id=None,
                        match_score=None,
                        match_type=None
                    )
                    result_upd = await session.execute(stmt_update)
                    print(f"Updated {result_upd.rowcount} Transaction records.")

                    # 3. (Optional) Delete Documents
                    if delete_docs:
                        print("Deleting linked/uploaded Documents...")
                        # Interpreting "uploaded within that month" as created_at match?
                        # Or documents linked to the transactions?
                        # The prompt said "uploaded within that month".
                        stmt_del_docs = delete(FinancialDocument).where(
                            extract('month', FinancialDocument.created_at) == month,
                            extract('year', FinancialDocument.created_at) == year
                        )
                        result_docs = await session.execute(stmt_del_docs)
                        print(f"Deleted {result_docs.rowcount} FinancialDocument records.")

            except Exception as e:
                print(f"Error during reset: {e}")
                await session.rollback()
                raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Database Reset Utility")
    parser.add_argument("--month", type=str, help="Target month in MM/YYYY format")
    parser.add_argument("--all", action="store_true", help="Delete all data")
    parser.add_argument("--delete-docs", action="store_true", help="Delete documents uploaded in the target month (only with --month)")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()

    if not args.all and not args.month:
        print("Error: Must specify --all or --month MM/YYYY")
        sys.exit(1)
        
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(reset_db(args.month, args.all, args.delete_docs, args.force))
