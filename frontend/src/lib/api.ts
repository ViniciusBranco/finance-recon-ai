import axios from 'axios';

// --- Interfaces based on Backend Models ---

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
}

export interface FinancialDocument {
    id: string; // UUID
    filename: string;
    original_filename?: string;
    doc_type: string; // 'RECEIPT' | 'BANK_STATEMENT' | 'UNKNOWN'
    status: string; // 'PENDING' | 'PROCESSED' | 'ERROR'
    created_at: string; // ISO string
    raw_text?: string;
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

    const response = await apiClient.post<UploadResponse>('/recon/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

export const getDocuments = async (docType?: string): Promise<FinancialDocument[]> => {
    const response = await apiClient.get<FinancialDocument[]>('/recon/documents', {
        params: { doc_type: docType }
    });
    return response.data;
};

export const deleteDocument = async (id: string): Promise<void> => {
    await apiClient.delete(`/recon/documents/${id}`);
};

export const resetWorkspace = async (): Promise<void> => {
    await apiClient.delete('/recon/reset');
};

export const getTransactions = async (unlinkedOnly: boolean = false, docType?: string): Promise<Transaction[]> => {
    const response = await apiClient.get<Transaction[]>('/recon/transactions', {
        params: { unlinked_only: unlinkedOnly, doc_type: docType },
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
