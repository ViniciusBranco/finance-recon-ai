# Finance Recon AI 💰🤖

> **Automação de Conciliação Financeira com Inteligência Artificial e Auditoria Fiscal.**

O **Finance Recon AI** é uma solução de engenharia de dados financeiros projetada para eliminar o trabalho manual de bater extratos bancários com notas fiscais e automatizar a conformidade contábil. O sistema emprega uma estratégia híbrida de ingestão, reconciliação N:1 para parcelamentos e um motor de RAG especializado em regras da Receita Federal.

![Status](https://img.shields.io/badge/Status-v1.5--beta%20Multi--Provider-green)
![Stack](https://img.shields.io/badge/AI%20Core-LangGraph%20%2B%20FAISS-violet)
![Stack](https://img.shields.io/badge/LLM-Gemini%20%2F%20GPT--5.2%20%2F%20Ollama-orange)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=fff)](#)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=fff)](#)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=fff)](#)

## ✨ Funcionalidades Core (v1.5)

* 🧠 **TaxExpertAgent (Multi-Provider RAG):** Agente especializado em IRPF/Livro-Caixa operando com Gemini 2.5 Flash/Pro e GPT-5.2.
* 🔄 **Reconciliação N:1 (Parcelamento):** Algoritmo capaz de identificar e vincular múltiplas transações bancárias (parcelas) a uma única Nota Fiscal.
* ⚡ **Ingestão Determinística (Fast-Track):** Parsers Regex para Itaú (Utilidades/Débito) e DANFE, reduzindo latência de minutos para milissegundos.
* 📈 **Telemetria de Custos:** Rastreamento de tokens e conversão dinâmica de custos de análise (USD para BRL).
* 📑 **Exportador Carnê-Leão:** Geração de CSVs padronizados conforme o layout da Receita Federal Brasileira.

## 🚀 Engineering Highlights

1.  **Quota Guard & Throttling:**
    Controle rigoroso de RPM (5 req/min) com intervalos de 13s para estabilidade no Free Tier do Gemini.
    
2.  **Persistência JSONB:**
    Armazenamento integral das análises fiscais e checklists para auditoria retroativa e faturamento.

3.  **UI de Auditoria Fiscal:**
    Interface em React/Tailwind v4 com suporte a Markdown para justificativas legais e badges de Risco de Glosa.

## 🏗️ Arquitetura

| Serviço | Tech Stack | Responsabilidade |
| :--- | :--- | :--- |
| **API Server** | FastAPI / SQLAlchemy | Orquestração, Persistência e Endpoints de Relatórios. |
| **Tax Engine** | LangChain / FAISS | RAG para análise de dedutibilidade e citações da IN 1500. |
| **LLM Factory** | Gemini / GPT / Ollama | Abstração dinâmica de modelos via variáveis de ambiente. |
| **Database** | PostgreSQL 15 | Storage de documentos, metadados de custo e análises. |

## 📅 Backlog (Próximos Passos)

- [ ] **UI Batch Progress:** Visualização de progresso em tempo real durante o processamento em lote.
- [ ] **Daily Rate Fetcher:** Atualização automática da taxa USD/BRL via API financeira.
- [ ] **Multi-User Tenant:** Separação lógica de dados por consultório/profissional.

---
*Desenvolvido com foco em Clean Code, Performance e Rigor Contábil.*