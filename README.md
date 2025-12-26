# Finance Recon AI 💰🤖

> **Automação de Conciliação Financeira com Inteligência Artificial e Auditoria Fiscal.**

O **Finance Recon AI** é uma solução de engenharia de dados financeiros projetada para eliminar o trabalho manual de bater extratos bancários com notas fiscais e automatizar a conformidade contábil. O sistema emprega uma estratégia híbrida de ingestão, reconciliação N:1 para parcelamentos e um motor de RAG especializado em regras da Receita Federal.

![Status](https://img.shields.io/badge/Status-v1.4--beta%20Tax%20Engine-blue)
![Stack](https://img.shields.io/badge/AI%20Core-LangGraph%20%2B%20FAISS-violet)
![Stack](https://img.shields.io/badge/LLM-Ollama%20%2F%20OpenAI%20Factory-orange)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=fff)](#)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=fff)](#)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=fff)](#)

## ✨ Funcionalidades Core (v1.4)

* 🧠 **TaxExpertAgent (RAG Local):** Agente especializado em IRPF/Livro-Caixa para profissionais de saúde. Utiliza vetores FAISS baseados na IN 1500/2014 e Perguntão IRPF 2025.
* 🔄 **Reconciliação N:1 (Parcelamento):** Algoritmo capaz de identificar e vincular múltiplas transações bancárias (parcelas) a uma única Nota Fiscal de alto valor.
* 🏗️ **LLM Factory Pattern:** Suporte modular para alternar entre inferência local (Ollama/Qwen) e Cloud (OpenAI GPT-4o) via variáveis de ambiente.
* 🛡️ **Time-Aware Audit:** Injeção dinâmica de data atual para validação rigorosa de "Regime de Caixa" e detecção de lançamentos futuros.
* ⚡ **Ingestão Híbrida:** Pipeline adaptativo (Pandas + LLM Vision) para processar PDFs protegidos, imagens e CSVs instantaneamente.

## 🚀 Engineering Highlights (Último Sprint)

1.  **Resiliência de Output (JSON Hardening):**
    Implementação de limpeza via Regex e *Few-Shot Prompting* para combater o desvio de formato (Markdown) em modelos 7B, garantindo a integridade do `PydanticOutputParser`.
    
2.  **Motor de Reconciliação Fracionário:**
    Adoção de lógica transação-cêntrica com tolerância de centavos (R$ 1,00) para lidar com arredondamentos bancários em boletos parcelados.

3.  **Persistência Unicode:**
    Padronização de encoding `utf-8-sig` para garantir a integridade de acentuação em extratos de bancos tradicionais (Itaú/Bradesco).

## 🏗️ Arquitetura

| Serviço | Tech Stack | Responsabilidade |
| :--- | :--- | :--- |
| **API Server** | FastAPI / SQLAlchemy | Orquestração, Validação Fiscal e Endpoints REST. |
| **Tax Engine** | LangChain / FAISS | RAG para análise de dedutibilidade e citações legais. |
| **LLM Factory** | Ollama / OpenAI | Abstração de modelos de linguagem (Local/Cloud). |
| **Database** | PostgreSQL 15 | Persistência de documentos, transações e histórico fiscal. |

## 📅 Backlog (Próximos Passos)

- [ ] **Stability Fix:** Resolver definitivamente o `OUTPUT_PARSING_FAILURE` em cenários de contexto inflado (NFs densas).
- [ ] **Persistence Layer:** Implementar armazenamento em `JSONB` das análises de dedutibilidade para auditoria histórica.
- [ ] **Livro-Caixa Generator:** Geração de relatório consolidado pronto para importação no Carnê-Leão Web.
- [ ] **Tax UI:** Interface para exibição de citações legais e indicadores de "Risco de Glosa" no card de transação.

---
*Desenvolvido com foco em Clean Code, Performance e Rigor Contábil.*