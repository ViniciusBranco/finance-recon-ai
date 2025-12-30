# Finance Recon AI 💰🤖

> **Automação de Conciliação Financeira com Inteligência Artificial e Auditoria Fiscal.**

O **Finance Recon AI** é uma solução de engenharia de dados financeiros projetada para eliminar o trabalho manual de bater extratos bancários com notas fiscais e automatizar a conformidade contábil. O sistema emprega uma estratégia híbrida de ingestão, reconciliação N:1 para parcelamentos e um motor de RAG especializado em regras da Receita Federal.

![Status](https://img.shields.io/badge/Status-v1.5.1--stable-green)
![Stack](https://img.shields.io/badge/AI%20Core-LangGraph%20%2B%20FAISS-violet)
![Stack](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-orange)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=fff)](#)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=fff)](#)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=fff)](#)

## ✨ Funcionalidades Core (v1.5)

* 🧠 **TaxExpertAgent (Multi-Provider RAG):** Agente especializado em IRPF/Livro-Caixa operando com Gemini 2.5 Flash.
* 🔄 **Isolamento por Competência:** Gerenciamento de workspace segmentado por Mês/Ano, permitindo uploads e conciliações independentes por período fiscal.
* 🛡️ **Proteção de Histórico:** Trava de segurança (`is_finalized`) que impede a deleção de transações e documentos já exportados em relatórios oficiais.
* ⚡ **Ingestão Determinística (Fast-Track):** Extração avançada de beneficiários e identificadores numéricos (DARF/GPS) via Regex e intersecção de tokens.
* 📈 **Telemetria de Custos:** Rastreamento granular de tokens e conversão dinâmica de custos de análise (USD para BRL).

## 🚀 Engineering Highlights

1.  **Persistent History Protection:** Relatórios gerados com UUID são salvos em disco (`/app/exports`) e vinculados ao banco de dados para conferência futura e preview.
2.  **Workspace Scoping:** Refatoração do motor de expurgo para suportar limpeza seletiva (apenas não-conciliados ou mês completo), respeitando a integridade dos relatórios salvos.
3.  **UI de Auditoria Sincronizada:** Dashboard em Tailwind v4 com filtros de status fiscal e indicadores de cota com alertas visuais (Pulse/Ping) para limites de API.

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
- [ ] **Dynamic Batch Scaling:** Refatorar o endpoint `analyze-batch` para aceitar um parâmetro `all_pending: bool` ou calcular automaticamente o limite.
- [ ] **Account Plan Keywords:** Expandir a lista de palavras-chave no backend (ex: adicionar "neodent", "straumann").
- [ ] **Progressive Batching:** Implementar um loop no Frontend que chame o endpoint `/analyze-batch` sucessivamente respeitando o throttling de 13s.
- [ ] **Quota Management:** Implementar um sistema de gerenciamento de cotas que permita visualizar o uso da cota atual e o limite máximo, e que permita reabrir a cota se necessário.

---
*Desenvolvido com foco em Clean Code, Performance e Rigor Contábil.*