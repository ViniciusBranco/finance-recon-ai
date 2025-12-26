from pydantic import BaseModel, Field
from typing import Optional, List

class TaxAnalysisResult(BaseModel):
    classificacao: str = Field(..., description="Status da classificação (e.g., Dedutível, Não Dedutível, Parcial)")
    categoria: str = Field(..., description="Categoria da despesa segundo o Livro Caixa")
    mes_lancamento: str = Field(..., description="Mês e ano de lançamento (título)")
    checklist: str = Field(..., description="Status de verificação dos documentos e requisitos")
    risco_glosa: str = Field(..., description="Nível de risco e motivo")
    comentario: str = Field(..., description="Justificativa legal e explicação")
    citacao_legal: Optional[str] = Field(None, description="Artigos e leis citados (ex: Art. 104 IN 1500)")

class TaxAnalysisResponse(BaseModel):
    id: str
    transaction_id: str
    classification: str
    category: Optional[str] = None
    month: Optional[str] = None
    justification_text: Optional[str] = None
    legal_citation: Optional[str] = None
    is_manual_override: bool
    
    class Config:
        from_attributes = True

class TaxAnalysisUpdate(BaseModel):
    classification: str
    category: str
    justification_text: Optional[str] = None
    legal_citation: Optional[str] = None

