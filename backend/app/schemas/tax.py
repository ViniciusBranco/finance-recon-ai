from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID

class TaxPendency(BaseModel):
    code: str = Field(..., description="Código curto da pendência (ex: DOC_MISSING, CNPJ_INVALID)")
    detail: str = Field(..., description="Descrição detalhada da pendência para o usuário")

class TaxAnalysisResult(BaseModel):
    classificacao: Literal["Dedutível", "Não Dedutível", "Parcialmente Dedutível", "Depende"] = Field(
        ..., description="Classificação fiscal final baseada na IN 1500/2014 e regime de caixa."
    )
    natureza: Literal["custeio", "terceiros", "empregados", "bem_de_capital", "pessoal", "incerto"] = Field(
        ..., description="Natureza econômica da despesa para segregação contábil."
    )
    categoria: str = Field(..., description="Categoria sugerida para o Livro Caixa (ex: Aluguel, Material de Consumo).")
    mes_lancamento: str = Field(..., description="Mês e ano do efetivo pagamento no formato MM/AAAA.")
    valor_total: float = Field(..., description="Valor total identificado no documento ou comprovante.")
    fornecedor_nome: Optional[str] = Field(None, description="Nome ou Razão Social do prestador/vendedor.")
    fornecedor_cpf_cnpj: Optional[str] = Field(None, description="CPF ou CNPJ limpo (apenas números) do fornecedor.")
    checklist: List[str] = Field(..., description="Lista de verificações realizadas (ex: 'Comprovante vinculado', 'Data válida').")
    risco_glosa: Literal["Baixo", "Médio", "Alto"] = Field(..., description="Nível de risco de rejeição pela Receita Federal.")
    comentario: str = Field(..., description="Justificativa lógica e detalhada da análise em Português.")
    citacao_legal: Optional[str] = Field(None, description="Citação específica da base legal (ex: Art. 104 da IN RFB 1500/2014).")
    pendencias: List[TaxPendency] = Field(default_factory=list, description="Lista de inconsistências ou documentos faltantes.")
    confianca: float = Field(ge=0, le=1, description="Nível de confiança do modelo na extração (0.0 a 1.0).")

class TaxAnalysisResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    classification: str
    category: Optional[str] = None
    month: Optional[str] = None
    risk_level: Optional[str] = None
    justification_text: Optional[str] = None
    legal_citation: Optional[str] = None
    raw_analysis: Optional[TaxAnalysisResult] = None # Objeto completo para o frontend
    is_manual_override: bool
    created_at: datetime
    
    # Usage Metadata
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    estimated_cost_brl: Optional[float] = None
    model_version: Optional[str] = None

    class Config:
        from_attributes = True

class TaxAnalysisUpdate(BaseModel):
    classification: str
    category: str
    justification_text: Optional[str] = None
    legal_citation: Optional[str] = None