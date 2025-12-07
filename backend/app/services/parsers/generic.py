from .base import DocumentParser
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.config import settings
from app.schemas.document import FinancialDocument

class GenericLLMParser(DocumentParser):
    def __init__(self):
        self.llm = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model="qwen2.5:7b",
            temperature=0.1,
            format="json"
        )
        self.parser = JsonOutputParser(pydantic_object=FinancialDocument)
        self.prompt = PromptTemplate(
            template="""Analyze the following text from a Brazilian financial document.
            
            **Classification Rules:**
            - usage of words like "Fatura", "Vencimento", "Limite de crédito", "Saldo", "Pagamento Mínimo" -> "BANK_STATEMENT" (Credit Card Bill/Extract).
            - usage of words like "Cupom Fiscal", "NFC-e", "Extrato", "Comprovante" or a single transaction -> "RECEIPT".

            **Extraction Rules:**
            - **Date**: Extract the main document date (e.g., due date for bills, transaction date for receipts). Convert "DD/MM/YYYY" to ISO 8601 "YYYY-MM-DD".
            - **Amount**: Extract the TOTAL amount ('Valor Total', 'Valor a pagar'). 
              - Handle Brazilian format: "1.000,00" -> 1000.00. 
              - "R$" is the currency symbol.
            - **Merchant/Bank**: The name of the issuer (e.g., "Nubank", "Restaurante X").

            **Return JSON ONLY:**
            {format_instructions}

            **Input Text:**
            {text}
            """,
            input_variables=["text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )
        self.chain = self.prompt | self.llm | self.parser

    @classmethod
    def detect(cls, text: str) -> bool:
        return True # Fallback

    def extract(self, text: str) -> dict:
        try:
            # We invoke the chain synchronously here because the parser interface is sync-ish 
            # (though we might be running in a threadpool). 
            # LangChain .invoke is valid.
            result = self.chain.invoke({"text": text})
            return {
                "doc_type": result.get("doc_type", "UNKNOWN"),
                "date": result.get("date"),
                "amount": result.get("amount"),
                "merchant_or_bank": result.get("merchant_or_bank")
            }
        except Exception as e:
            # Return partial or error indicator? 
            # For now, propagate error or return empty
            raise e
