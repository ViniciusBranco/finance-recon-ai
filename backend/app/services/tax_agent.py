import os
import re
import json
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from app.core.config import settings
from app.schemas.tax import TaxAnalysisResult
from app.core.llm_factory import LLMFactory

# Paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
VECTOR_STORE_DIR = os.path.join(BACKEND_ROOT, "knowledge", "vector_store")

class TaxExpertAgent:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaxExpertAgent, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.embeddings = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url=settings.OLLAMA_BASE_URL
        )
        
        # Load Vector Store
        # Ensure ingest.py has been run
        if not os.path.exists(VECTOR_STORE_DIR):
            raise RuntimeError(f"Vector store not found at {VECTOR_STORE_DIR}. Please run ingest.py first.")
            
        self.vector_store = FAISS.load_local(
            VECTOR_STORE_DIR, 
            self.embeddings, 
            allow_dangerous_deserialization=True
        )
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 5})
        
        # Use Factory
        self.llm = LLMFactory.get_llm(temperature=0.1)
        
        self.parser = PydanticOutputParser(pydantic_object=TaxAnalysisResult)

        system_prompt = """Você é um Especialista Tributário Sênior (TaxExpertAgent) focado em Livro-Caixa e Carnê-Leão para Dentistas no Brasil.
        
        Sua missão é classificar transações financeiras com base nas regras da Receita Federal (Perguntão IRPF, Instruções Normativas) recuperadas do contexto.
        
        REGRAS DE CLASSIFICAÇÃO (CASH BASIS / REGIME DE CAIXA):
        1. Dedutibilidade:
           - Apenas despesas NECESSÁRIAS para a manutenção da atividade profissional e percepção da receita.
           - Ex: Aluguel, condomínio, luz/água do consultório, materiais odontológicos, salários de auxiliares, ISS, CRO.
           - Deve ter comprovante idôneo (NF, Recibo com CPF/CNPJ).
           - Deve ter sido PAGA no ano-calendário (Regime de Caixa).
        
        2. Não Dedutível:
           - Bens de capital / Investimentos (durabilidade > 1 ano, ex: Cadeira Odontológica, Raio-X). Estes sofrem depreciação (não deduz integralmente na compra).
           - Despesas pessoais (escola dos filhos, supermercado de casa).
           - Tarifas bancárias (exceto conta exclusivamente profissional, mas verifique regras específicas).
        
        INSTRUÇÕES DE FORMATAÇÃO:
        Analise os dados da transação e o comprovante fornecido.
        Retorne APENAS um objeto JSON compatível com o schema fornecido.
        {format_instructions}
        
        Preencha os campos com precisão:
        - classificacao: "Dedutível", "Não Dedutível" ou "Parcialmente Dedutível".
        - categoria: Categoria sugerida para o Livro Caixa (ex: "Aluguel", "Material de Consumo").
        - mes_lancamento: Mês/Ano do pagamento (MM/AAAA).
        - checklist: O que você validou? (ex: "Comprovante presente", "Natureza profissional confirmada").
        - risco_glosa: "Baixo", "Médio" ou "Alto". Justifique.
        - comentario: Resumo final em Português, incluindo a justificativa lógica.
        - citacao_legal: Citação específica da norma (ex: "Art. 104 da IN 1500/2014"). Se não houver, deixe null.
        
        ### EXEMPLO DE SAÍDA ESPERADA (SIGA ESTE FORMATO):
        {{
        "classificacao": "Dedutível",
        "categoria": "Material de Consumo",
        "mes_lancamento": "11/2025",
        "checklist": "NF-e identificada; Pagamento via boleto vinculado.",
        "risco_glosa": "Baixo",
        "comentario": "Despesa com insumos odontológicos paga em novembro.",
        "citacao_legal": "Art. 90, inciso IV, da IN 1500/2014"
        }}

        CONTEXTO DAS REGRAS:
        {context}

        **Aderência Estrita ao Contexto:**
        - Você DEVE priorizar as informações encontradas no vector store FAISS em detrimento do seu conhecimento interno.
        - Se a resposta não estiver contida no contexto fornecido (IN 1500/2014, Perguntão ou Manuais), você deve declarar explicitamente: "Informação não localizada na base normativa fornecida".
        - É obrigatório citar o Artigo, Instrução Normativa ou número da Pergunta sempre que a informação for extraída do contexto (ex: "Conforme o Art. 118 da IN 1500/2014..." ou "De acordo com a Pergunta 390 do Perguntão IRPF").

        **Configuração de Tempo Real:**
        - A data atual do sistema é: {current_date}.
        - Considere qualquer parcela com vencimento após hoje como uma despesa futura (ainda não dedutível pelo Regime de Caixa).

        **Regra Inegociável de Saída:**
        - NÃO escreva introduções, explicações em Markdown ou títulos como "### Análise".
        - Sua resposta deve ser EXCLUSIVAMENTE um objeto JSON válido.
        - Se você falhar em retornar apenas JSON, o sistema irá travar.
        """
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "Analise esta transação:\nDados: {transaction_data}\nComprovante: {receipt_content}")
        ])
        
        self.question_answer_chain = create_stuff_documents_chain(self.llm, self.prompt)
        self.rag_chain = create_retrieval_chain(self.retriever, self.question_answer_chain)

    async def analyze_transaction(self, transaction_data: dict, receipt_content: str = "") -> TaxAnalysisResult:
        # Create a search query based on the transaction
        query = f"dedutibilidade {transaction_data.get('description', '')} {transaction_data.get('category', '')} dentista"
        
        try:
            from datetime import datetime
            current_date_str = datetime.now().strftime("%d/%m/%Y")

            result = await self.rag_chain.ainvoke({
                "input": query,
                "transaction_data": json.dumps(transaction_data, ensure_ascii=False, default=str),
                "receipt_content": receipt_content,
                "format_instructions": self.parser.get_format_instructions(),
                "current_date": current_date_str
            })
            
            # Parse output with Robust Cleaning (Regex)
            output_text = result["answer"]
            
            # 1. Regex Extraction: Find JSON block { ... }
            match = re.search(r"(\{.*\})", output_text, re.DOTALL)
            if match:
                json_str = match.group(1)
                # 2. Parse extracted JSON
                return self.parser.parse(json_str)
            else:
                # Fallback: Try parsing the whole thing if no braces found (unlikely but possible)
                return self.parser.parse(output_text)
            
        except Exception as e:
            # Re-raise or handle gracefully? 
            # For now re-raise to see errors in dev
            print(f"Error in Tax Agent: {e}")
            raise e

tax_agent = TaxExpertAgent()
