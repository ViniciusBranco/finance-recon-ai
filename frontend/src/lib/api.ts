import axios from 'axios';

// --- Interfaces based on Backend Models ---

export interface TaxAnalysis {
    id: string;
    transaction_id: string;
    classification: string;
    category: string | null;
    month: string | null;
    justification_text: string | null;
    legal_citation: string | null;
    risk_level?: string | null;
    raw_analysis?: {
        checklist?: string[];
        comentario?: string;
    } | null;
    is_manual_override: boolean;
}

export interface Transaction {
    id: string; // UUID
    document_id: string; // UUID
    merchant_name: string;
    date: string; // YYYY-MM-DD
    amount: number;
    category: string | null;
    receipt_id: string | null; // UUID
    match_score: number | null;
    match_type: string | null; // 'AUTO' | 'MANUAL' | null
    tax_analysis?: TaxAnalysis | null;
}

export interface FinancialDocument {
    id: string; // UUID
    filename: string;
    original_filename?: string;
    doc_type: string; // 'RECEIPT' | 'BANK_STATEMENT' | 'UNKNOWN'
    status: string; // 'PENDING' | 'PROCESSED' | 'ERROR'
    created_at: string; // ISO string
    raw_text?: string;
    linked_transaction_id?: string | null;
    transactions?: Transaction[];
}

export interface ReconciliationStats {
    total_transactions: number;
    reconciled_transactions: number;
    unreconciled_transactions: number;
    accuracy: number;
}

export interface UploadResponse {
    message: string;
    file_id?: string;
    transactions_extracted?: number;
    doc_type?: string;
    error?: string;
    status?: string;
}

// --- API Client Setup ---

const API_BASE_URL = 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// --- API Functions ---

export const uploadDocument = async (file: File, docType?: 'BANK_STATEMENT' | 'RECEIPT', password?: string): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (password) {
        formData.append('password', password);
    }
    if (docType) {
        formData.append('expected_type', docType);
    }

    // Dynamic timeout based on file size
    // Minimum 300 seconds (300000ms = 5 minutes) to allow for slow local LLM inference
    const timeout = Math.max(300000, file.size / 20);

    const response = await apiClient.post<UploadResponse>('/recon/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
        timeout: timeout
    });
    return response.data;
};

export const uploadStatement = async (file: File, password?: string): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (password) {
        formData.append('password', password);
    }
    // Dynamic timeout
    const timeout = Math.max(300000, file.size / 20);
    const response = await apiClient.post<UploadResponse>('/recon/upload/statement', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: timeout
    });
    return response.data;
};

export const uploadReceipt = async (file: File, password?: string): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (password) {
        formData.append('password', password);
    }
    // Dynamic timeout
    const timeout = Math.max(300000, file.size / 20);
    const response = await apiClient.post<UploadResponse>('/recon/upload/receipt', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: timeout
    });
    return response.data;
};

export const getDocuments = async (docType?: string, taxStatus?: string): Promise<FinancialDocument[]> => {
    // Note: If backend endpoint /recon/documents supports tax_status filtering (it probably doesn't yet based on previous file view),
    // we should update backend or filter client-side. The user request asks to "pass it to the backend".
    // I will assume backend needs update or supports it (I checked reconciliation.py, it doesn't currently support tax_status in get_documents).
    // I will pass it anyway as requested "Update getDocuments to accept... pass it to backend", and likely need to update backend too.
    // Wait, the prompt says "Update getDocuments... and pass it to the backend".
    // I should check backend support in next step or now. The previous view of `reconciliation.py` showed `get_documents` does NOT accept `tax_status`.
    // I will update the frontend first as requested here.
    const response = await apiClient.get<FinancialDocument[]>('/recon/documents', {
        params: { doc_type: docType, tax_status: taxStatus }
    });
    return response.data;
};

export const deleteDocument = async (id: string): Promise<void> => {
    await apiClient.delete(`/recon/documents/${id}`);
};

export const resetWorkspace = async (): Promise<void> => {
    await apiClient.delete('/recon/reset');
};

export const updateDocument = async (id: string, data: { date?: string; amount?: number }): Promise<FinancialDocument> => {
    const response = await apiClient.patch<FinancialDocument>(`/recon/documents/${id}`, data);
    return response.data;
};

export const getTransactions = async (unlinkedOnly: boolean = false, docType?: string, taxStatus?: string): Promise<Transaction[]> => {
    const response = await apiClient.get<Transaction[]>('/recon/transactions', {
        params: { unlinked_only: unlinkedOnly, doc_type: docType, tax_status: taxStatus },
    });
    return response.data;
};

export const triggerReconciliation = async (): Promise<ReconciliationStats> => {
    const response = await apiClient.post<ReconciliationStats>('/recon/reconcile');
    return response.data;
};

export const manualMatch = async (transactionId: string, receiptId: string, force: boolean = false): Promise<void> => {
    await apiClient.post(`/recon/transactions/${transactionId}/match`, { receipt_id: receiptId, force });
};

export const analyzeIndividual = async (transactionId: string): Promise<TaxAnalysis> => {
    // Note: The backend endpoint is /tax/analyze/{id} based on inferred route from user request
    // But checking current codebase, the TaxAnalysis endpoint was mapped.
    // Let's check backend routes if needed, but user explicitly said:
    // "It must call POST /api/v1/tax/analyze/{txnId}"
    // Assuming such endpoint exists or I should mapping to existing /tax-analysis/{id} if that's what it was.
    // Wait, line 165 has `analyzeTax` pointing to `/tax-analysis/${transactionId}`. 
    // The user request says: "Add analyzeIndividual(txnId)... It must call POST /api/v1/tax/analyze/{txnId}."
    // I will follow instruction literally for the URL.
    const response = await apiClient.post<TaxAnalysis>(`/tax/analyze/${transactionId}`);
    return response.data;
};

export const analyzeBatch = async (limit: number = 1): Promise<{ message: string; status: string }> => {
    const response = await apiClient.post<{ message: string; status: string }>(`/tax/analyze-batch`, null, {
        params: { limit_batch: limit }
    });
    return response.data;
};

export const updateTaxAnalysis = async (transactionId: string, data: {
    classification: string;
    category: string;
    justification_text?: string;
    legal_citation?: string;
}): Promise<TaxAnalysis> => {
    const response = await apiClient.put<TaxAnalysis>(`/tax-analysis/${transactionId}`, data);
    return response.data;
};
