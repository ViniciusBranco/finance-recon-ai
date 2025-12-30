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

export interface TaxReport {
    id: string; // UUID
    month: number;
    year: number;
    filename: string;
    total_deductible: number;
    created_at: string;
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

export const uploadDocument = async (file: File, docType?: 'BANK_STATEMENT' | 'RECEIPT', password?: string, month?: number, year?: number): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (password) formData.append('password', password);
    if (docType) formData.append('expected_type', docType);
    if (month) formData.append('month', month.toString());
    if (year) formData.append('year', year.toString());

    // Dynamic timeout based on file size
    const timeout = Math.max(300000, file.size / 20);

    const response = await apiClient.post<UploadResponse>('/recon/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: timeout
    });
    return response.data;
};

export const uploadStatement = async (file: File, password?: string, month?: number, year?: number): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (password) formData.append('password', password);
    if (month) formData.append('month', month.toString());
    if (year) formData.append('year', year.toString());

    const timeout = Math.max(300000, file.size / 20);
    const response = await apiClient.post<UploadResponse>('/recon/upload/statement', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: timeout
    });
    return response.data;
};

export const uploadReceipt = async (file: File, password?: string, month?: number, year?: number): Promise<UploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    if (password) formData.append('password', password);
    if (month) formData.append('month', month.toString());
    if (year) formData.append('year', year.toString());

    const timeout = Math.max(300000, file.size / 20);
    const response = await apiClient.post<UploadResponse>('/recon/upload/receipt', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: timeout
    });
    return response.data;
};

export const getDocuments = async (docType?: string, taxStatus?: string, month?: number, year?: number): Promise<FinancialDocument[]> => {
    const response = await apiClient.get<FinancialDocument[]>('/recon/documents', {
        params: { doc_type: docType, tax_status: taxStatus, month, year }
    });
    return response.data;
};

export const deleteDocument = async (id: string): Promise<void> => {
    await apiClient.delete(`/recon/documents/${id}`);
};

export const clearWorkspace = async (month: number, year: number, onlyUnlinked: boolean): Promise<void> => {
    await apiClient.delete('/recon/clear-workspace', {
        params: { month, year, only_unlinked: onlyUnlinked }
    });
};

export const updateDocument = async (id: string, data: { date?: string; amount?: number }): Promise<FinancialDocument> => {
    const response = await apiClient.patch<FinancialDocument>(`/recon/documents/${id}`, data);
    return response.data;
};

export const getTransactions = async (unlinkedOnly: boolean = false, docType?: string, taxStatus?: string, month?: number, year?: number): Promise<Transaction[]> => {
    const response = await apiClient.get<Transaction[]>('/recon/transactions', {
        params: { unlinked_only: unlinkedOnly, doc_type: docType, tax_status: taxStatus, month, year },
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

// --- Tax Report Functions ---

export const getTaxReports = async (): Promise<TaxReport[]> => {
    const response = await apiClient.get<TaxReport[]>('/tax/reports');
    return response.data;
};

export const generateTaxReport = async (month: number, year: number): Promise<TaxReport> => {
    const response = await apiClient.post<TaxReport>('/tax/reports/generate', null, {
        params: { month, year }
    });
    return response.data;
};

export const getTaxReportPreview = async (reportId: string): Promise<Record<string, any>[]> => {
    const response = await apiClient.get<Record<string, any>[]>(`/tax/reports/${reportId}/preview`);
    return response.data;
};

export const getTaxReportDownloadUrl = (reportId: string): string => {
    return `${API_BASE_URL}/tax/reports/${reportId}/download`;
};
