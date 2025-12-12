# Finance Recon AI 💰🤖

> **Automação de Conciliação Financeira com Inteligência Artificial e Auditoria Ativa.**

O **Finance Recon AI** é uma solução de engenharia de dados financeiros projetada para eliminar o trabalho manual de bater extratos bancários com notas fiscais. O sistema emprega uma estratégia híbrida de ingestão (Pandas para estruturados, LLM para não-estruturados) e oferece uma interface de auditoria ativa com travas de segurança rigorosas.

![Status](https://img.shields.io/badge/Status-v1.3%20Audit%20Ready-success)
![Stack](https://img.shields.io/badge/AI%20Core-LangGraph%20%2B%20Ollama-violet)
![Stack](https://img.shields.io/badge/Performance-Pandas%20Fast%20Track-orange)

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=fff)](#)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=fff)](#)
[![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=000)](#)
[![Tailwind](https://img.shields.io/badge/Tailwind-v4-38B2AC?logo=tailwind-css&logoColor=white)](#)

## ✨ Funcionalidades Core (v1.3)

* ⚡ **Ingestão Híbrida Inteligente:** Pipeline adaptativo que usa `Pandas` para leitura instantânea de CSVs (bypass de GPU) e Agentes LLM apenas para PDFs/Imagens complexos.
* 🖱️ **Auditoria Visual (Drag-and-Drop):** Interface de arrastar e soltar com scroll independente para conciliação manual ágil.
* 🛡️ **Travas de Segurança (Strict Matching):** Validação rígida de Data e Valor no match manual. Discrepâncias de D+0 ou centavos acionam alertas de confirmação (`HTTP 409`).
* 📊 **KPI Orientado à Auditoria:** Cálculo de acurácia focado na **Cobertura de Notas Fiscais** (Audit Completeness), ignorando o ruído natural do extrato bancário.
* 🔐 **Suporte a Arquivos Protegidos:** Detecção e tratamento de PDFs criptografados com interação via UI.

## 🚀 Engineering Highlights (Sprint v1.3)

O sistema evoluiu de uma ferramenta de "match passivo" para uma plataforma de auditoria robusta:

1.  **CSV Fast-Track (IOPS Optimization):**
    Implementação de rota expressa para arquivos `.csv`. O parser detecta delimitadores e encodings automaticamente, processando milhares de linhas em milissegundos sem onerar a VRAM/LLM.

2.  **Safety Net Logic (Zero Tolerance):**
    Refatoração do algoritmo de *Manual Match*. O sistema agora aplica tolerância zero para diferenças de data ou valor, exigindo *override* explícito do usuário (Modal de Confirmação) para garantir integridade contábil.

3.  **UX Reativa & DndKit:**
    Migração para `@dnd-kit` com zonas de drop visuais e feedback tátil. Scrollbars independentes nas colunas permitem auditar listas de tamanhos desproporcionais (ex: 80 transações vs 5 notas).

## 🏗️ Arquitetura

O projeto segue uma arquitetura baseada em microsserviços containerizados:

| Serviço | Tech Stack | Responsabilidade |
| :--- | :--- | :--- |
| **API Server** | FastAPI / Pydantic | Orquestração, Validação de Regras de Negócio e Endpoints REST. |
| **Worker AI** | LangChain / LangGraph | Agentes para extração de dados não-estruturados (PDF/Img). |
| **Data Engine** | Pandas / NumPy | Processamento vetorial de alta performance para CSV/OFX. |
| **Frontend** | React / TanStack Query | SPA com *Optimistic UI Updates* e gestão de estado complexa. |
| **Database** | PostgreSQL 15 | Persistência relacional e integridade referencial. |

## 🛠️ Como Rodar (Local)

### Pré-requisitos
* Docker & Docker Compose v2+
* Python 3.11+ (Recomendado para tooling local)

### Instalação

1.  **Clone e Configure:**
    ```bash
    git clone [https://github.com/ViniciusBranco/finance-recon-ai.git](https://github.com/ViniciusBranco/finance-recon-ai.git)
    cd finance-recon-ai
    cp .env.example .env
    ```

2.  **Suba a Stack:**
    ```bash
    docker compose up -d --build
    ```

3.  **Acesse:**
    * **Frontend:** `http://localhost:5173`
    * **API Docs:** `http://localhost:8000/docs`

---
*Desenvolvido com foco em Clean Code, Performance e Rigor Contábil.*