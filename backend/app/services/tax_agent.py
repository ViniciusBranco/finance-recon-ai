import os
import re
import json
import uuid
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# ...


from langchain_community.callbacks import get_openai_callback
from app.core.config import settings
from app.schemas.tax import TaxAnalysisResult
from app.core.llm_factory import LLMFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import TaxAnalysis

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
        self.llm = LLMFactory.get_llm(temperature=0.0)
        
        self.parser = PydanticOutputParser(pydantic_object=TaxAnalysisResult)

        system_prompt = """Você é um Especialista Tributário Sênior (TaxExpertAgent) focado em Livro-Caixa e Carnê-Leão para Dentistas no Brasil.
        
        DO NOT REPEAT THE INPUT DATA. YOUR TASK IS ANALYSIS, NOT ECHOING.
        
        Sua missão é classificar transações financeiras com base nas regras da Receita Federal (Perguntão IRPF, Instruções Normativas) recuperadas do contexto.
        
        REGRAS DE CLASSIFICAÇÃO (CASH BASIS / REGIME DE CAIXA):
        1. Dedutibilidade:
           - Apenas despesas NECESSÁRIAS para a manutenção da atividade profissional e percepção da receita.
           - Ex: Aluguel, condomínio, luz/água do consultório, materiais odontológicos, salários de auxiliares, ISS, CRO.
           - Deve ter comprovante idôneo (NF, Recibo com CPF/CNPJ).
           - Deve ter sido PAGA no ano-calendário (Regime de Caixa).
           - Regra Especial: Pagamentos para "Surya Dental" são considerados despesas dedutíveis de insumos odontológicos.
           - Professional Utilities: For a Dentist (Livro-Caixa), expenses like VIVO, SABESP, and Electricity for the office are ALWAYS 'Dedutível' and 'natureza: custeio'.
        
        2. Não Dedutível:
           - Bens de capital / Investimentos (durabilidade > 1 ano, ex: Cadeira Odontológica, Raio-X). Estes sofrem depreciação (não deduz integralmente na compra).
           - Despesas pessoais (escola dos filhos, supermercado de casa).
           - Tarifas bancárias (exceto conta exclusivamente profissional, mas verifique regras específicas).
        
        RULES FOR VALUE EXTRACTION:
        - The 'valor_total' field MUST strictly match the 'amount' provided in the transaction data. DO NOT invent numbers.
        - Cite the law: If classification is Dedutível for utilities, cite 'Art. 104, inciso III da IN RFB 1500/2014'.
        
        INSTRUÇÕES DE FORMATAÇÃO:
        Analise os dados da transação e o comprovante fornecido.
        Retorne APENAS um objeto JSON compatível com o schema fornecido, iniciando com {{ e terminando com }}.
        {format_instructions}
        
        Preencha os campos com precisão:
        - classificacao: "Dedutível", "Não Dedutível" ou "Parcialmente Dedutível".
        - natureza: "custeio", "terceiros", "empregados", "bem_de_capital", "pessoal", "incerto".
        - categoria: Categoria sugerida para o Livro Caixa (ex: "Aluguel", "Material de Consumo").
        - mes_lancamento: Mês/Ano do pagamento (MM/AAAA).
        - valor_total: Valor numérico total da despesa (float).
        - checklist: Lista de validações (ex: ["Comprovante presente", "Natureza confirmada"]).
        - risco_glosa: "Baixo", "Médio" ou "Alto". Justifique.
        - comentario: Resumo final em Português, incluindo a justificativa lógica.
        - citacao_legal: Citação específica da norma (ex: "Art. 104 da IN 1500/2014"). Se não houver, deixe null.
        - confianca: Nível de confiança da análise (0.0 a 1.0).
        
        ### EXEMPLO DE SAÍDA ESPERADA (SIGA ESTE FORMATO):
        {{
        "classificacao": "Dedutível",
        "natureza": "custeio",
        "categoria": "Material de Consumo",
        "mes_lancamento": "11/2025",
        "valor_total": 150.00,
        "checklist": ["NF-e identificada", "Pagamento via boleto vinculado"],
        "risco_glosa": "Baixo",
        "comentario": "Despesa com insumos odontológicos paga em novembro.",
        "citacao_legal": "Art. 90, inciso IV, da IN 1500/2014",
        "confianca": 0.95
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
        - Sua resposta deve ser EXCLUSIVAMENTE um objeto JSON válido contendo apenas as chaves do schema.
        - Se você falhar em retornar apenas JSON, o sistema irá travar.
        """
        
        # Determine if we need OLLAMA specific wrapping (or just apply generally as it's safer)
        human_template = """
        ### TRANSACTION TO ANALYZE ###
        Dados: {transaction_data}
        Comprovante: {receipt_content}
        ### END TRANSACTION ###
        """

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_template)
        ])
        

        self.question_answer_chain = None # Deprecated
        
        # Helper for formatting docs
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        # LCEL Construction
        self.rag_chain = (
            RunnablePassthrough.assign(
                context=(lambda x: x["input"]) | self.retriever | format_docs
            )
            | self.prompt
            | self.llm
        )

    async def analyze_transaction(self, transaction_data: dict, receipt_content: str = "", db_session: AsyncSession = None) -> TaxAnalysisResult:
        # 1. Check DB for existing analysis
        if db_session and transaction_data.get("id"):
            try:
                txn_uuid = uuid.UUID(str(transaction_data["id"]))
                stmt = select(TaxAnalysis).where(TaxAnalysis.transaction_id == txn_uuid)
                result = await db_session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing and existing.raw_analysis:
                    return TaxAnalysisResult(**existing.raw_analysis)
            except Exception as e:
                print(f"Error checking existing tax analysis: {e}")

        # Create a search query based on the transaction
        query = f"dedutibilidade {transaction_data.get('description', '')} {transaction_data.get('category', '')} dentista"
        
        try:
            from datetime import datetime
            current_date_str = datetime.now().strftime("%d/%m/%Y")

            # Token Tracking Variables
            cb_prompt_tokens = 0
            cb_completion_tokens = 0
            cb_total_tokens = 0
            cb_cost = 0.0

            provider = settings.LLM_PROVIDER.upper()
            
            # Execute LLM Call with provider-specific tracking
            if provider == "OPENAI":
                with get_openai_callback() as cb:
                    result = await self.rag_chain.ainvoke({
                        "input": query,
                        "transaction_data": json.dumps(transaction_data, ensure_ascii=False, default=str),
                        "receipt_content": receipt_content,
                        "format_instructions": self.parser.get_format_instructions(),
                        "current_date": current_date_str
                    })
                    cb_prompt_tokens = cb.prompt_tokens
                    cb_completion_tokens = cb.completion_tokens
                    cb_total_tokens = cb.total_tokens
                    cb_cost = cb.total_cost
            else:
                # OLLAMA or GEMINI
                result = await self.rag_chain.ainvoke({
                    "input": query,
                    "transaction_data": json.dumps(transaction_data, ensure_ascii=False, default=str),
                    "receipt_content": receipt_content,
                    "format_instructions": self.parser.get_format_instructions(),
                    "current_date": current_date_str
                })
                
                if provider == "GEMINI":
                    # Correctly access usage metadata from AIMessage
                    usage = {}
                    if hasattr(result, "usage_metadata") and result.usage_metadata:
                        usage = result.usage_metadata
                    elif hasattr(result, "response_metadata") and result.response_metadata:
                        usage = result.response_metadata.get("usage_metadata") or result.response_metadata

                    if usage:
                        prompt_tokens = usage.get("prompt_token_count", 0) or usage.get("input_tokens", 0)
                        completion_tokens = usage.get("candidates_token_count", 0) or usage.get("output_tokens", 0)
                        total_tokens = usage.get("total_token_count", 0) or usage.get("total_tokens", 0)
                        
                        # Gemini 1.5 Pro Pricing (approximate for 2025 context)
                        # Input: $1.25 / 1M tokens
                        # Output: $5.00 / 1M tokens
                        cost_input = (prompt_tokens / 1_000_000) * 1.25
                        cost_output = (completion_tokens / 1_000_000) * 5.00
                        total_cost = cost_input + cost_output
                        
                        cb_prompt_tokens = prompt_tokens
                        cb_completion_tokens = completion_tokens
                        cb_total_tokens = total_tokens
                        cb_cost = total_cost
                        
                        print(f"Gemini Usage: {prompt_tokens} in, {completion_tokens} out. Cost: ${total_cost:.6f}")

            
            # Parse output with Robust Cleaning (Regex)
            if hasattr(result, "content"):
                output_text = result.content
            elif isinstance(result, dict) and "answer" in result:
                output_text = result["answer"]
            else:
                output_text = str(result)
            
            parsed_result = None
            # 1. Regex Extraction: Find JSON block { ... }
            match = re.search(r"(\{.*\})", output_text, re.DOTALL)
            if match:
                json_str = match.group(1)
                
                # Validation: Check if it looks like an echo (has 'merchant' but no 'classificacao')
                # This is a heuristic to catch cases where LLM just returns the input JSON
                check_dict = json.loads(json_str)
                if ("merchant_name" in check_dict or "description" in check_dict) and "classificacao" not in check_dict:
                    print(f"LLM Hallucination (Echo) detected. Output: {output_text}")
                    raise ValueError("LLM echoed input instead of analyzing")
                
                parsed_result = self.parser.parse(json_str)
            else:
                # Fallback
                print(f"LLM Output (No JSON block found): {output_text}")
                parsed_result = self.parser.parse(output_text)

            # 3. Persist to DB
            # 3. Persist to DB
            if db_session and transaction_data.get("id") and parsed_result:
                try:
                    # Currency Conversion
                    cost_brl = cb_cost * settings.USD_BRL_RATE
                    print(f"Analysis Cost: ${cb_cost:.6f} | R${cost_brl:.6f}") # Log final cost

                    # Retrieve model name directly from LLM instance
                    model_id = getattr(self.llm, "model_name", getattr(self.llm, "model", f"{provider.lower()}-model"))

                    txn_uuid = uuid.UUID(str(transaction_data["id"]))
                    new_analysis = TaxAnalysis(
                        transaction_id=txn_uuid,
                        classification=parsed_result.classificacao,
                        category=parsed_result.categoria,
                        month=parsed_result.mes_lancamento,
                        risk_level=parsed_result.risco_glosa,
                        justification_text=parsed_result.comentario,
                        legal_citation=parsed_result.citacao_legal,
                        raw_analysis=parsed_result.model_dump(),
                        is_manual_override=False,
                        # Token Usage Persistence
                        prompt_tokens=cb_prompt_tokens,
                        completion_tokens=cb_completion_tokens,
                        total_tokens=cb_total_tokens,
                        estimated_cost=cb_cost,
                        estimated_cost_brl=cost_brl,
                        model_version=model_id
                    )
                    db_session.add(new_analysis)
                    # We don't commit here to allow caller to manage transaction scope (atomicity)
                    await db_session.flush() # Ensure ID is generated and constraints checked
                except Exception as e:
                    print(f"Error saving tax analysis: {e}")

            # Logic Guard: Value Mismatch Protection
            input_amount_val = None
            try:
                input_amount_val = float(transaction_data.get("amount", 0.0))
            except:
                pass

            if parsed_result and input_amount_val is not None:
                # LLM often returns positive values even for negative debit transactions.
                # Tax Analysis usually cares about the absolute cost.
                # But if the mismatch is just sign or slight rounding, we trust the Input.
                # If LLM invented a number (e.g. 100.0 vs 59.73), we force the Input.
                
                llm_val = abs(parsed_result.valor_total)
                inp_val = abs(input_amount_val)
                
                if abs(llm_val - inp_val) > 0.1:
                    print(f"Logic Guard: Adjusting LLM Value ({llm_val}) to match Transaction ({inp_val})")
                    parsed_result.valor_total = inp_val
            
            return parsed_result
            
        except Exception as e:
            # Re-raise or handle gracefully? 
            # For now re-raise to see errors in dev
            print(f"Error in Tax Agent: {e}")
            raise e
            


tax_agent = TaxExpertAgent()
