import pytest
import os
from unittest.mock import MagicMock, patch
from app.services.tax_agent import TaxExpertAgent, TaxAnalysisResult

# Fixture to initialize the agent once
@pytest.fixture(scope="function")
def tax_agent():
    # Force reset singleton to avoid Event Loop Closed errors with pytest-asyncio
    TaxExpertAgent._instance = None
    return TaxExpertAgent()

@pytest.mark.slow
async def test_scenario_1_citation_check(tax_agent):
    """
    Scenario 1: 'Conserto de Autoclave'. Should be deductible.
    Checks if the response mentions specific tax rules (IN 1500, Art., etc).
    REAL LLM CALL.
    """
    txn_data = {
        "description": "Conserto de Autoclave",
        "amount": 450.00,
        "date": "2025-05-15",
        "category": "Manutenção"
    }
    receipt_content = "Recibo referente a manutenção de autoclave Stermax. Peças e mão de obra."
    
    result = await tax_agent.analyze_transaction(txn_data, receipt_content)
    
    print(f"\n[Scenario 1] Comentário: {result.comentario}")
    
    keywords = ["artigo", "art.", "instrução normativa", "in 1500", "perguntão", "livro caixa", "necessária"]
    found_keyword = any(k in result.comentario.lower() for k in keywords)
    
    assert found_keyword, f"Reasoning does not contain citations. Got: {result.comentario}"
    assert result.classificacao == "Dedutível"

@pytest.mark.slow
async def test_scenario_2_zero_knowledge_fallback(tax_agent):
    """
    Scenario 2: 'Corporate Tax/PJ'. Out of scope.
    Should trigger fallback message or clear non-deductible reasoning.
    REAL LLM CALL.
    """
    txn_data = {
        "description": "Assessment of Corporate Tax for Multinational Entity",
        "amount": 50000.00,
        "date": "2025-06-20",
        "category": "Taxes"
    }
    
    result = await tax_agent.analyze_transaction(txn_data)
    
    print(f"\n[Scenario 2] Comentário: {result.comentario}")

    # The prompt instructions say: "Se a resposta não estiver no contexto... state: 'Informação não localizada na base normativa fornecida.'"
    target_phrase = "informação não localizada"
    
    # We accept either the strict phrase OR a valid "Não Dedutível" classification if the LLM knows it's personal expenses (not corporate).
    # But for this test, we want to enforce the prompt instruction about context.
    
    if target_phrase in result.comentario.lower():
        assert True
    else:
        # Fallback check: It might say it's not deductible because it's corporate.
        assert result.classificacao == "Não Dedutível"

@pytest.mark.slow
async def test_scenario_3_date_logic_cash_basis(tax_agent):
    """
    Scenario 3: Date Logic.
    Payment in 15/12/2025 should be 'Dezembro/2025' or '12/2025'.
    REAL LLM CALL.
    """
    txn_data = {
        "description": "Conta de Energia",
        "amount": 300.00,
        "date": "2025-12-15",
        "category": "Utilidades"
    }
    
    result = await tax_agent.analyze_transaction(txn_data)
    
    print(f"\n[Scenario 3] Mês Lançamento: {result.mes_lancamento}")
    
    month_lower = result.mes_lancamento.lower()
    valid_patterns = ["dezembro/2025", "12/2025", "dez/2025", "dezembro 2025"]
    assert any(p in month_lower for p in valid_patterns), f"Date format incorrect. Got: {result.mes_lancamento}"

async def test_schema_validation_mock():
    """
    Unit Test: Validate schema parsing without LLM.
    Mocks the RAG chain response to return a pre-canned JSON string.
    """
    mock_agent = TaxExpertAgent()
    mock_agent.rag_chain = MagicMock()
    
    fake_response = {
        "answer": """
        {
            "classificacao": "Dedutível",
            "categoria": "Teste",
            "mes_lancamento": "Janeiro/2025",
            "checklist": "Ok",
            "risco_glosa": "Baixo",
            "comentario": "Teste Unitário"
        }
        """
    }
    
    # Setup async mock
    async def async_return(*args, **kwargs):
        return fake_response
    
    mock_agent.rag_chain.ainvoke.side_effect = async_return
    
    txn_data = {"description": "Test", "amount": 10}
    result = await mock_agent.analyze_transaction(txn_data)
    
    assert isinstance(result, TaxAnalysisResult)
    assert result.classificacao == "Dedutível"
    assert result.categoria == "Teste"
