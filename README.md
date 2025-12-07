# Finance Recon AI 💰🤖

> **Automação de Conciliação Financeira com Inteligência Artificial e Processamento Local.**

O **Finance Recon AI** é uma solução de engenharia de dados financeiros projetada para eliminar o trabalho manual de bater extratos bancários com notas fiscais. Utilizando pipelines de ETL robustos e agentes de IA, o sistema ingere PDFs (inclusive protegidos por senha), OFX e imagens, realiza o *matching* semântico e entrega relatórios de auditoria com precisão.

![Status](https://img.shields.io/badge/Status-Production%20Ready-success)
![Stack](https://img.shields.io/badge/AI%20Core-LangGraph%20%2B%20Ollama-violet)
![Stack](https://img.shields.io/badge/Backend-FastAPI%20%2B%20Async-009688)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=fff)](#)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=fff)](#)
[![Postgres](https://img.shields.io/badge/Postgres-15-336791?logo=postgresql&logoColor=white)](#)
[![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=000)](#)
[![Tailwind](https://img.shields.io/badge/Tailwind-v4-38B2AC?logo=tailwind-css&logoColor=white)](#)

## ✨ Funcionalidades Core (v1.2)

* 🔄 **Reconciliação Automatizada:** Algoritmo híbrido (Regras + LLM) que cruza datas, valores e nomes de estabelecimentos para sugerir *matches* com % de precisão.
* 🔐 **Suporte a Arquivos Protegidos:** Detecção automática de PDFs criptografados com prompt interativo de senha no Frontend, sem falhar o upload.
* 📊 **Dashboard de Auditoria:** Filtros dinâmicos (*All Transactions*, *Matched Only*, *Unlinked Only*) para foco total nas exceções.
* 🧠 **Smart Extraction:** Parser inteligente que resolve nomes de estabelecimentos complexos (ex: "PG * SMARTFIT" -> "SmartFit") ignorando ruídos bancários.
* 🛡️ **Prevenção de Duplicidade:** Mecanismo de hash e limpeza de estado que impede uploads duplicados ou estados inconsistentes no banco.

## 🚀 Engineering Highlights (Último Sprint)

O sistema recebeu atualizações críticas de estabilidade e UX:

1.  **Tratamento de Exceções de PDF:** Implementação de retry loop no Frontend para arquivos com senha (`PASSWORD_REQUIRED`), limpando registros pendentes no banco para evitar "Zumbi Data".
2.  **Refinamento de ETL:** Correção na lógica de `processor.py` para priorizar campos de metadados (`merchant_name`) sobre texto cru, aumentando drasticamente a taxa de reconhecimento de transações.
3.  **Cálculo de Acurácia:** Normalização do cálculo de confiança do *match* para exibição correta na UI (ex: `Match Confidence: 98%`).

## 🏗️ Arquitetura

O projeto segue uma arquitetura baseada em microsserviços containerizados:

| Serviço | Tech Stack | Responsabilidade |
| :--- | :--- | :--- |
| **API Server** | FastAPI, Pydantic, SQLAlchemy (Async) | Orquestração de uploads, gestão de estado e endpoints REST. |
| **Worker AI** | LangChain, LangGraph | Agentes de extração de dados e lógica difusa de conciliação. |
| **Frontend** | React, TypeScript, TanStack Query | SPA reativa com gestão de estado otimista e feedback em tempo real. |
| **Database** | PostgreSQL 15 | Persistência relacional de transações, documentos e links de conciliação. |
| **Inference** | Ollama (Local) | LLM rodando *on-premise* para privacidade total dos dados financeiros. |

## 🛠️ Como Rodar (Local)

### Pré-requisitos
* Docker & Docker Compose v2+
* Node.js 20+ (apenas se for rodar fora do container)
* Python 3.11+

### Instalação Rápida

1.  **Clone e Configure:**
    ```bash
    git clone [https://github.com/seu-repo/finance-recon-ai.git](https://github.com/seu-repo/finance-recon-ai.git)
    cd finance-recon-ai
    cp .env.example .env
    ```

2.  **Suba a Stack:**
    ```bash
    # O build inicial pode demorar devido à compilação das deps de Python
    docker compose up -d --build
    ```

3.  **Acesse:**
    * **Frontend:** `http://localhost:5173`
    * **API Docs:** `http://localhost:8000/docs`

---
*Desenvolvido com foco em Clean Code e Performance.*