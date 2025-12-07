import React, { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import { getDocuments, getTransactions, triggerReconciliation, deleteDocument, resetWorkspace, uploadDocument } from '../lib/api';
import type { Transaction, FinancialDocument, ReconciliationStats } from '../lib/api';
import { RefreshCw, CheckCircle, FileText, Link as LinkIcon, Trash2, Upload, Loader2, AlertCircle } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { toast } from 'sonner';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const formatDate = (dateString: string) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('pt-BR');
};

const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(amount);
};

// Compact Dropzone Component
interface CompactDropzoneProps {
    label: string;
    docType?: 'BANK_STATEMENT' | 'RECEIPT';
    onUploadSuccess: (filename: string) => void;
}

const CompactDropzone: React.FC<CompactDropzoneProps> = ({ label, docType, onUploadSuccess }) => {
    const [uploading, setUploading] = useState(false);
    const [currentFile, setCurrentFile] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;

        setError(null);
        setUploading(true);

        const processFile = async (file: File, pwd?: string) => {
            const result = await uploadDocument(file, docType, pwd);

            if (result.status === 'partial_success') {
                toast.warning(`Uploaded ${file.name}`, {
                    description: result.error || 'File processed but parsing incomplete',
                    className: "bg-yellow-50 border-yellow-200 text-yellow-800"
                });
            } else if (result.doc_type === 'BANK_STATEMENT') {
                const count = result.transactions_extracted || 0;
                if (count === 0) {
                    toast.warning("Bank Statement Uploaded", {
                        description: "No transactions parsed. Please check the file format.",
                        className: "bg-yellow-50 border-yellow-200 text-yellow-800"
                    });
                } else {
                    toast.success("Bank Statement Uploaded", {
                        description: `${count} transactions found. Now upload Receipts to reconcile.`,
                        className: "bg-blue-50 border-blue-200 text-blue-800"
                    });
                }
            } else if (result.doc_type === 'RECEIPT') {
                toast.success("Receipt Uploaded", {
                    description: "Ready for reconciliation. Upload Bank Statement if needed.",
                    className: "bg-purple-50 border-purple-200 text-purple-800"
                });
            } else {
                toast.success("File uploaded successfully.");
            }
            onUploadSuccess(file.name);
        };

        try {
            for (const file of acceptedFiles) {
                setCurrentFile(file.name);
                try {
                    await processFile(file);
                } catch (err: any) {
                    console.error("Upload error:", err);
                    const msg = err.response?.data?.detail || err.message || "Upload failed";

                    if (err.response?.status === 400 && (msg === "PASSWORD_REQUIRED" || msg.includes("Invalid Password"))) {
                        const password = prompt(`Password required for ${file.name}:`);
                        if (password) {
                            try {
                                await processFile(file, password);
                                continue; // Success on retry
                            } catch (retryErr: any) {
                                const retryMsg = retryErr.response?.data?.detail || retryErr.message;
                                toast.error("Retry Failed", { description: retryMsg });
                                setError(retryMsg); // Make sure to set error if retry fails
                            }
                        } else {
                            toast.error("Upload Cancelled", { description: "Password required." });
                            setError("Password required");
                        }
                    } else if (err.response?.status === 409) {
                        toast.error("Duplicate File", { description: msg });
                        setError(msg);
                    } else {
                        toast.error("Upload Failed", { description: msg });
                        setError(msg);
                    }
                }
            }
            setCurrentFile(null);
        } catch (globalErr) {
            console.error("Critical upload error", globalErr);
        } finally {
            setUploading(false);
            if (!error) setCurrentFile(null);
        }
    }, [onUploadSuccess, docType, error]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        disabled: uploading
    });

    return (
        <div
            {...getRootProps()}
            className={cn(
                "border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors mb-4 relative overflow-hidden",
                isDragActive
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/10"
                    : uploading
                        ? "border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 cursor-not-allowed"
                        : "border-slate-300 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-600 bg-slate-50 dark:bg-slate-900/50"
            )}
        >
            <input {...getInputProps()} />

            {uploading ? (
                <div className="flex flex-col items-center justify-center gap-2 text-blue-600 dark:text-blue-400 py-1">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <div className="text-sm font-medium truncate max-w-[200px]">
                        Uploading {currentFile}...
                    </div>
                </div>
            ) : error ? (
                <div className="flex flex-col items-center gap-1 text-red-500 py-1">
                    <div className="flex items-center gap-1">
                        <AlertCircle className="w-4 h-4" />
                        <span className="text-sm font-medium">Error</span>
                    </div>
                    <span className="text-xs max-w-full truncate px-2" title={error}>{error}</span>
                </div>
            ) : (
                <div className="flex flex-col items-center gap-2 text-slate-500 dark:text-slate-400">
                    <Upload className="w-5 h-5 mb-1" />
                    <span className="text-sm font-medium">{label}</span>
                    <span className="text-xs text-slate-400 dark:text-slate-500 hidden sm:inline">Drag & drop files here</span>
                </div>
            )}
        </div>
    );
};


export const ReconWorkbench: React.FC = () => {
    const queryClient = useQueryClient();
    const [reconciling, setReconciling] = useState(false);
    const [lastReconResult, setLastReconResult] = useState<ReconciliationStats | null>(null);
    const [resetKey, setResetKey] = useState(0);
    const [lastBankFile, setLastBankFile] = useState<string | null>(null);
    const [lastReceiptFile, setLastReceiptFile] = useState<string | null>(null);
    const [filter, setFilter] = useState<'ALL' | 'MATCHED' | 'UNLINKED'>('ALL');

    // Fetch Transactions (Bank Feed) - Explicit Type
    const { data: transactions, isLoading: loadingTx, isError: errorTx } = useQuery<Transaction[]>({
        queryKey: ['transactions', 'BANK_STATEMENT'],
        queryFn: () => getTransactions(false, 'BANK_STATEMENT'),
    });

    // Fetch Documents (Receipts) - Explicit Type
    const { data: documents, isLoading: loadingDocs, isError: errorDocs } = useQuery<FinancialDocument[]>({
        queryKey: ['documents', 'RECEIPT'],
        queryFn: () => getDocuments('RECEIPT'),
    });

    // Reconcile Mutation
    const mutation = useMutation({
        mutationFn: triggerReconciliation,
        onMutate: () => setReconciling(true),
        onSuccess: (data: ReconciliationStats) => {
            setLastReconResult(data);
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
            queryClient.invalidateQueries({ queryKey: ['documents'] });
        },
        onSettled: () => setReconciling(false),
    });

    const deleteMutation = useMutation({
        mutationFn: deleteDocument,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['documents'] });
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
        },
    });

    const resetMutation = useMutation({
        mutationFn: resetWorkspace,
        onSuccess: () => {
            setLastReconResult(null);
            setLastBankFile(null);
            setLastReceiptFile(null);
            setResetKey(prev => prev + 1);
            queryClient.invalidateQueries({ queryKey: ['documents'] });
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
        }
    });

    // Filtering Logic: The API now filters, so we just fallback to empty array if loading
    const bankTransactions = transactions || [];
    const receiptDocuments = documents || [];

    // Refresh function for uploads
    const refreshData = (filename?: string, type?: 'BANK_STATEMENT' | 'RECEIPT') => {
        if (filename) {
            if (type === 'BANK_STATEMENT') setLastBankFile(filename);
            else if (type === 'RECEIPT') setLastReceiptFile(filename);
        }
        queryClient.invalidateQueries({ queryKey: ['documents'] });
        queryClient.invalidateQueries({ queryKey: ['transactions'] });
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-6">
                <div>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Reconciliation Workbench</h2>
                    <p className="text-slate-500 dark:text-slate-400">Match bank transactions with uploaded receipts.</p>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={() => {
                            if (confirm("DANGER: This will delete ALL transactions and documents. Are you sure?")) {
                                resetMutation.mutate();
                            }
                        }}
                        disabled={resetMutation.isPending}
                        className="px-4 py-2 rounded-lg font-medium text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 border border-transparent hover:border-red-200 dark:hover:border-red-900 transition-all text-sm"
                    >
                        {resetMutation.isPending ? "Clearing..." : "Clear All Data"}
                    </button>

                    <button
                        onClick={() => mutation.mutate()}
                        disabled={reconciling}
                        className={cn(
                            "flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-white shadow-sm transition-all",
                            reconciling
                                ? "bg-slate-400 cursor-not-allowed"
                                : "bg-blue-600 hover:bg-blue-700 active:scale-95"
                        )}
                    >
                        <RefreshCw className={cn("w-5 h-5", reconciling && "animate-spin")} />
                        {reconciling ? "Reconciling..." : "Run Auto-Reconcile"}
                    </button>
                </div>
            </div>

            {lastReconResult && (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 flex items-start gap-3">
                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 mt-0.5" />
                    <div>
                        <p className="font-semibold text-green-900 dark:text-green-300">Reconciliation Complete</p>
                        <p className="text-green-800 dark:text-green-400 text-sm">
                            {lastReconResult.reconciled_transactions} matches found. Accuracy: {(lastReconResult.accuracy * 100).toFixed(1)}%
                        </p>
                    </div>
                </div>
            )}

            {/* Split View */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

                {/* Left Column: Bank Feed */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                            <div className="w-2 h-6 bg-blue-500 rounded-full"></div>
                            Bank Feed
                            <span className="text-xs font-normal px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded-full text-slate-500">
                                {bankTransactions.length} items
                            </span>
                        </h3>

                        <div className="flex items-center gap-2">
                            <select
                                value={filter}
                                onChange={(e) => setFilter(e.target.value as any)}
                                className="text-sm border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 py-1 px-2 focus:ring-2 focus:ring-blue-500"
                            >
                                <option value="ALL">All Transactions</option>
                                <option value="MATCHED">Matched Only</option>
                                <option value="UNLINKED">Unlinked Only</option>
                            </select>
                            {lastBankFile && (
                                <span className="ml-auto text-xs text-slate-400 font-normal hidden sm:inline-block">
                                    Last: <span className="text-slate-600 dark:text-slate-300 truncate max-w-[100px] inline-block align-bottom" title={lastBankFile}>{lastBankFile}</span>
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Zone A: Bank Statement Upload */}
                    <CompactDropzone
                        key={`bank-${resetKey}`}
                        label="Upload Bank Statement (PDF, CSV, OFX)"
                        docType="BANK_STATEMENT"
                        onUploadSuccess={(fname) => refreshData(fname, 'BANK_STATEMENT')}
                    />

                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden min-h-[500px]">
                        {loadingTx ? (
                            <div className="flex justify-center items-center h-64 text-slate-400">Loading transactions...</div>
                        ) : errorTx ? (
                            <div className="flex justify-center items-center h-64 text-red-500">Error loading data.</div>
                        ) : bankTransactions.length === 0 ? (
                            <div className="flex justify-center items-center h-64 text-slate-400">No transactions found.</div>
                        ) : (
                            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                                {bankTransactions
                                    .filter(tx => {
                                        if (filter === 'MATCHED') return tx.receipt_id;
                                        if (filter === 'UNLINKED') return !tx.receipt_id;
                                        return true;
                                    })
                                    .map((tx: Transaction) => {
                                        const isMatched = !!tx.receipt_id;
                                        // Find linked receipt filename if exists
                                        const linkedDoc = isMatched && tx.receipt_id
                                            ? documents?.find(d => d.id === tx.receipt_id)
                                            : null;

                                        return (
                                            <li key={tx.id} className={cn(
                                                "p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group border-l-4",
                                                isMatched
                                                    ? "bg-emerald-50/30 dark:bg-emerald-900/10 border-emerald-500"
                                                    : "border-transparent bg-white dark:bg-slate-900"
                                            )}>
                                                <div className="flex justify-between items-start mb-1">
                                                    <span className="font-medium text-slate-900 dark:text-slate-100 line-clamp-1" title={tx.merchant_name}>
                                                        {tx.merchant_name}
                                                    </span>
                                                    <span className={cn(
                                                        "font-mono font-semibold",
                                                        tx.amount < 0 ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"
                                                    )}>
                                                        {formatCurrency(tx.amount)}
                                                    </span>
                                                </div>
                                                <div className="flex justify-between items-center text-sm text-slate-500 dark:text-slate-400">
                                                    <span>{formatDate(tx.date)}</span>

                                                    {isMatched ? (
                                                        <div className="flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400 text-xs font-medium bg-emerald-100 dark:bg-emerald-900/30 px-2.5 py-1 rounded-full border border-emerald-200 dark:border-emerald-800">
                                                            <LinkIcon className="w-3 h-3" />
                                                            {linkedDoc ? `Linked: ${linkedDoc.original_filename || linkedDoc.filename}` : `Matched (${(tx.match_score! * 100).toFixed(0)}%)`}
                                                        </div>
                                                    ) : (
                                                        <span className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">
                                                            Unlinked
                                                        </span>
                                                    )}
                                                </div>
                                            </li>
                                        );
                                    })}
                            </ul>
                        )}
                    </div>
                </div>

                {/* Right Column: Receipts Audit */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                            <div className="w-2 h-6 bg-purple-500 rounded-full"></div>
                            Receipts Audit
                            <span className="text-xs font-normal px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded-full text-slate-500">
                                {receiptDocuments.length} files
                            </span>
                            {lastReceiptFile && (
                                <span className="ml-auto text-xs text-slate-400 font-normal">
                                    Last: <span className="text-slate-600 dark:text-slate-300 truncate max-w-[150px] inline-block align-bottom">{lastReceiptFile}</span>
                                </span>
                            )}
                        </h3>
                    </div>

                    {/* Zone B: Receipts Upload */}
                    <CompactDropzone
                        key={`receipts-${resetKey}`}
                        label="Upload Receipts & Invoices (PDF, XML)"
                        docType="RECEIPT"
                        onUploadSuccess={(fname) => refreshData(fname, 'RECEIPT')}
                    />

                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden min-h-[500px]">
                        {loadingDocs ? (
                            <div className="flex justify-center items-center h-64 text-slate-400">Loading documents...</div>
                        ) : errorDocs ? (
                            <div className="flex justify-center items-center h-64 text-red-500">Error loading documents.</div>
                        ) : receiptDocuments.length === 0 ? (
                            <div className="flex justify-center items-center h-64 text-slate-400">No receipts uploaded.</div>
                        ) : (
                            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                                {receiptDocuments.map((doc: FinancialDocument) => {
                                    // Ensure strict typing for nested properties
                                    const isLinked = doc.transactions && doc.transactions.length > 0;
                                    const receiptTx = doc.transactions?.[0];

                                    return (
                                        <li key={doc.id} className="p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group">
                                            <div className="flex items-start gap-3">
                                                <div className="p-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-purple-600 dark:text-purple-400">
                                                    <FileText className="w-5 h-5" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex justify-between items-start">
                                                        <p className="font-medium text-slate-900 dark:text-slate-100 truncate pr-2" title={doc.original_filename || doc.filename}>
                                                            {doc.original_filename || doc.filename}
                                                        </p>
                                                        <div className="flex items-center gap-2">
                                                            {isLinked && (
                                                                <span className="flex-shrink-0 inline-flex items-center rounded-md bg-purple-50 px-2 py-1 text-xs font-medium text-purple-700 ring-1 ring-inset ring-purple-700/10 dark:bg-purple-400/10 dark:text-purple-400 dark:ring-purple-400/30">
                                                                    Linked
                                                                </span>
                                                            )}
                                                            <button
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    if (confirm('Delete this document?')) deleteMutation.mutate(doc.id);
                                                                }}
                                                                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-slate-400 hover:text-red-500 rounded"
                                                                title="Delete"
                                                            >
                                                                <Trash2 className="w-4 h-4" />
                                                            </button>
                                                        </div>
                                                    </div>

                                                    <div className="mt-1 flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                                                        {receiptTx ? (
                                                            <>
                                                                <span>{formatDate(receiptTx.date)}</span>
                                                                <span className="text-slate-300 dark:text-slate-700">•</span>
                                                                <span className="font-mono">{formatCurrency(receiptTx.amount)}</span>
                                                            </>
                                                        ) : (
                                                            <span className="italic opacity-70">No specific data extracted</span>
                                                        )}
                                                    </div>

                                                </div>
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </div>

            </div>
        </div>
    );
};
