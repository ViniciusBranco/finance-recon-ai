import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.services.tax_agent import TaxExpertAgent
from app.schemas.tax import TaxAnalysisResult

async def run_test():
    print("--- Starting Integration Test: Installment + Tax Analysis ---")
    
    # 1. Setup Data
    # Simulating the Bank Transaction (Installment Payment)
    transaction_data = {
        "date": "2025-11-10",
        "amount": -281.01,
        "merchant": "ITAU - SURYA DENTAL (Simulated Manual/Auto Match)",
        "description": "PAG BOLETO 12345"
    }

    # Simulating the Receipt OCR Content (The Full Invoice)
    receipt_content = """
    DANFE
    SURYA DENTAL COM PROD ODONT E FARM S/A
    CNPJ: 00.266.279.0001-50
    DATA DA EMISSÃO: 15/10/2025
    DESTINATÁRIO: ANA CAROLINA LOPES DE MORAES
    
    CÁLCULO DO IMPOSTO
    VALOR TOTAL DOS PRODUTOS: 845,73
    VALOR TOTAL DA NOTA: 845,73
    
    DADOS DO PRODUTO/SERVIÇO
    1. Resina Filtek Z350 XT - R$ 200,00
    2. Adesivo Single Bond - R$ 150,00
    ...
    
    FATURA / DUPLICATA
    Num    Venc       Valor
    001    10/11/2025  281,91
    002    10/12/2025  281,91
    003    10/01/2026  281,91
    """

    print(f"Input Transaction: {transaction_data}")
    print("Input Receipt text length:", len(receipt_content))

    # 2. Run Tax Analysis
    try:
        agent = TaxExpertAgent()
        print("Agent initialized. Running analysis...")
        
        result: TaxAnalysisResult = await agent.analyze_transaction(transaction_data, receipt_content)
        
        print("\n--- Analysis Result ---")
        print(result.model_dump_json(indent=2))
        
        # 3. Validation Logic
        failures = []
        
        # Check Classification
        if "Dedutível" not in result.classificacao:
            failures.append(f"Classification Mismatch: Expected 'Dedutível', Got '{result.classificacao}'")

        # Check Month (Must be November, Cash Basis)
        # Accept "Novembro/2025", "11/2025", "Novembro 2025"
        normalized_month = result.mes_lancamento.lower()
        if "nov" not in normalized_month and "11/2025" not in normalized_month:
            failures.append(f"Month Mismatch: Expected 'Novembro/2025' (Cash Basis), Got '{result.mes_lancamento}'")

        # Check Category (Livro Caixa)
        if not result.categoria:
             failures.append("Category is missing")

        # Check Citation
        if not result.citacao_legal:
             failures.append("Legal Citation is missing")
        elif "1500" not in result.citacao_legal and "pergunt" not in result.citacao_legal.lower():
             failures.append(f"Legal Citation mismatch: Expected 'IN 1500' or 'Perguntão', Got '{result.citacao_legal}'")
             
        if failures:
            print("\n❌ TEST FAILED:")
            for f in failures:
                print(f" - {f}")
        else:
            print("\n✅ TEST PASSED")
            print("Logic confirmed: Deductible Installment recognized in correct Cash Basis month.")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
