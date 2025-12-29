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
* 🔄 **Reconciliação Soberana:** Motor híbrido que suporta vínculos automáticos (janela de 45 dias para NF-e) e manuais (Drag-and-Drop) ignorando discrepâncias de data para respeitar o fato gerador bancário.
* ⚡ **Ingestão Determinística (Fast-Track):** Parsers Regex/Fuzzy para Itaú e DANFE com "Zero-Inference Policy" (datas e valores nulos forçam revisão em vez de assumir dados falsos).
* 📈 **Telemetria de Custos:** Rastreamento granular de tokens e conversão dinâmica de custos de análise (USD para BRL) integrada ao banco de dados.
* 📑 **Exportador Carnê-Leão:** Geração de CSVs padronizados conforme o layout da Receita Federal com mapeamento de plano de contas (P10.01.x).

## 🚀 Engineering Highlights

1.  **Quota Guard & Throttling:** Controle de RPM (5 req/min) com intervalos de 13s entre chamadas de IA para estabilidade e conformidade com limites de API.
2.  **Integridade Contábil (Nullable Schema):** Migração do banco para suportar datas e valores nulos, garantindo que o sistema nunca invente dados fiscais (User-in-the-Loop).
3.  **UI de Auditoria Sincronizada:** Interface React/Tailwind v4 com ordenação por valor absoluto e filtros sincronizados entre Extrato e Comprovantes.

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
- [ ] **Dynamic Batch Scaling:** Refatorar o endpoint analyze-batch para aceitar um parâmetro all_pending: bool ou calcular automaticamente o limite com base na cota restante retornada pelo /quota-status.
- [ ] **Account Plan Keywords:** Expandir a lista de palavras-chave no backend (ex: adicionar "neodent", "straumann") para que o código P10.01.00005 seja aplicado automaticamente mesmo se a IA classificar como "Material de Consumo" genérico.
- [ ] **Progressive Batching:** Implementar um loop no Frontend que chame o endpoint /analyze-batch sucessivamente até que não restem transações pendentes, respeitando os 13s de intervalo de forma transparente para o usuário.
- [ ] **Quota Management:** Implementar um sistema de gerenciamento de cotas que permita visualizar o uso da cota atual e o limite máximo, e que permita reabrir a cota se necessário.

---
*Desenvolvido com foco em Clean Code, Performance e Rigor Contábil.*