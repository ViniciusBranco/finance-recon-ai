import React, { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import {
    getDocuments,
    getTransactions,
    triggerReconciliation,
    deleteDocument,
    resetWorkspace,
    uploadDocument,
    manualMatch,
    analyzeTax
} from '../lib/api';
import type { Transaction, FinancialDocument, ReconciliationStats } from '../lib/api';
import { RefreshCw, CheckCircle, FileText, Link as LinkIcon, Trash2, Upload, Loader2, AlertCircle, AlertTriangle, Scale } from 'lucide-react';
import { TaxAnalysisPanel } from './TaxAnalysisPanel';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { toast } from 'sonner';
import { DndContext, useDraggable, useDroppable, DragOverlay } from '@dnd-kit/core';
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';

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

// --- Drag & Drop Components ---

interface DraggableReceiptProps {
    doc: FinancialDocument;
    isLinked: boolean;
    onDelete: (id: string) => void;
}

const DraggableReceipt: React.FC<DraggableReceiptProps> = ({ doc, isLinked, onDelete }) => {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: doc.id,
        data: doc,
        disabled: isLinked
    });

    const style = {
        transform: CSS.Translate.toString(transform),
        zIndex: isDragging ? 100 : undefined,
        opacity: isDragging ? 0.5 : 1
    };

    const receiptTx = doc.transactions?.[0];

    return (
        <div
            ref={setNodeRef}
            style={style}
            {...listeners}
            {...attributes}
            className={cn(
                "p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group cursor-grab active:cursor-grabbing",
                isLinked && "opacity-75 cursor-default"
            )}
        >
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
                                onPointerDown={(e) => e.stopPropagation()} // Prevent drag start match on delete
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (confirm('Delete this document?')) onDelete(doc.id);
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
        </div>
    );
};

interface DroppableTransactionProps {
    transaction: Transaction;
    isMatched: boolean;
    linkedDoc: FinancialDocument | undefined;
}

const DroppableTransaction: React.FC<DroppableTransactionProps> = ({ transaction: tx, isMatched, linkedDoc }) => {
    const { setNodeRef, isOver } = useDroppable({
        id: tx.id,
        disabled: isMatched
    });
    const [showTax, setShowTax] = useState(false);

    // Classification Colors
    const getTaxStatusColor = () => {
        if (!tx.tax_analysis) return "text-slate-400 bg-slate-100 dark:bg-slate-800 dark:text-slate-500 hover:text-blue-600 hover:bg-blue-50";
        const cls = tx.tax_analysis.classification.toLowerCase();
        if (cls.includes('dedutível') && !cls.includes('não')) return "text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-400";
        if (cls.includes('parcial')) return "text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20 dark:text-yellow-400";
        return "text-slate-500 bg-slate-100 dark:bg-slate-800 dark:text-slate-400";
    };

    return (
        <li
            ref={setNodeRef}
            className={cn(
                "p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group border-l-4 flex flex-col gap-3",
                isMatched
                    ? "bg-emerald-50/30 dark:bg-emerald-900/10 border-emerald-500"
                    : "border-transparent bg-white dark:bg-slate-900",
                isOver && !isMatched && "bg-blue-50 dark:bg-blue-900/20 border-blue-500 ring-1 ring-inset ring-blue-500/20"
            )}
        >
            <div className="flex justify-between items-start">
                <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-1">
                        <span className="font-medium text-slate-900 dark:text-slate-100 line-clamp-1" title={tx.merchant_name}>
                            {tx.merchant_name}
                        </span>
                        <span className={cn(
                            "font-mono font-semibold ml-2",
                            tx.amount < 0 ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"
                        )}>
                            {formatCurrency(tx.amount)}
                        </span>
                    </div>
                    <div className="flex justify-between items-center text-sm text-slate-500 dark:text-slate-400">
                        <span>{formatDate(tx.date)}</span>

                        <div className="flex items-center gap-2">
                            {isMatched && (
                                <button
                                    onClick={() => setShowTax(!showTax)}
                                    className={cn("p-1.5 rounded-md transition-colors flex items-center gap-1.5 text-xs font-medium border border-transparent", getTaxStatusColor(), showTax && "ring-2 ring-blue-500/20")}
                                    title="Tax Analysis"
                                >
                                    <Scale className="w-3.5 h-3.5" />
                                    {tx.tax_analysis?.classification || "Analyze"}
                                </button>
                            )}

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
                    </div>
                </div>
            </div>

            {showTax && isMatched && (
                <div className="pt-2 animate-in slide-in-from-top-2 duration-200">
                    <TaxAnalysisPanel
                        transactionId={tx.id}
                        analysis={tx.tax_analysis}
                        onClose={() => setShowTax(false)}
                    />
                </div>
            )}
        </li>
    );
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
                                const retryMsg = retryErr.code === 'ECONNABORTED' ? "Upload timed out" : (retryErr.response?.data?.detail || retryErr.message);
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
                    } else if (err.code === 'ECONNABORTED') {
                        const timeoutMsg = "Upload timed out. The file might be too large or the server is busy.";
                        toast.error("Upload Failed", { description: timeoutMsg });
                        setError(timeoutMsg);
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
            // If we had a successful upload logic that cleared error, we keep it cleared. 
            // If we had an error, it is set above.
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
    const [filter, setFilter] = useState<'ALL' | 'MATCHED' | 'UNLINKED'>('ALL');
    const [activeDoc, setActiveDoc] = useState<FinancialDocument | null>(null);

    // Conflict Modal State
    const [conflictModalOpen, setConflictModalOpen] = useState(false);
    const [pendingMatch, setPendingMatch] = useState<{ txnId: string, receiptId: string, message: string } | null>(null);

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
            setResetKey(prev => prev + 1);
            queryClient.invalidateQueries({ queryKey: ['documents'] });
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
        }
    });

    // Filtering Logic: The API now filters, so we just fallback to empty array if loading
    const bankTransactions = transactions || [];
    const receiptDocuments = documents || [];

    // Refresh function for uploads
    // Refresh function for uploads
    const refreshData = () => {
        queryClient.invalidateQueries({ queryKey: ['documents'] });
        queryClient.invalidateQueries({ queryKey: ['transactions'] });
    };

    // Manual Match Logic
    const handleDragStart = (event: DragStartEvent) => {
        setActiveDoc(event.active.data.current as FinancialDocument);
    };

    const handleDragEnd = async (event: DragEndEvent) => {
        const { active, over } = event;
        setActiveDoc(null);

        if (!over) return;

        const receiptId = active.id as string;
        const txnId = over.id as string;

        try {
            await manualMatch(txnId, receiptId, false);
            toast.success("Match Confirmed");
            // Trigger Tax Analysis in background
            analyzeTax(txnId).then(() => {
                toast.success("Tax Analysis Complete");
                queryClient.invalidateQueries({ queryKey: ['transactions'] });
            }).catch(e => console.error("Tax Analysis Trigger Failed", e));

            queryClient.invalidateQueries({ queryKey: ['transactions'] });
            queryClient.invalidateQueries({ queryKey: ['documents'] });
        } catch (err: any) {
            if (err.response?.status === 409) {
                const msg = err.response.data.detail?.replace("Discrepancy Detected:", "").trim();
                setPendingMatch({
                    txnId,
                    receiptId,
                    message: msg || "Discrepancy detected."
                });
                setConflictModalOpen(true);
            } else {
                toast.error("Match Failed", { description: err.message || "Unknown error" });
            }
        }
    };

    const confirmForceMatch = async () => {
        if (!pendingMatch) return;
        try {
            await manualMatch(pendingMatch.txnId, pendingMatch.receiptId, true);
            toast.success("Forced Match Confirmed");

            // Trigger Tax Analysis in background
            analyzeTax(pendingMatch.txnId).then(() => {
                toast.success("Tax Analysis Complete");
                queryClient.invalidateQueries({ queryKey: ['transactions'] });
            }).catch(e => console.error("Tax Analysis Trigger Failed", e));

            queryClient.invalidateQueries({ queryKey: ['transactions'] });
            queryClient.invalidateQueries({ queryKey: ['documents'] });
            setConflictModalOpen(false);
            setPendingMatch(null);
        } catch (err: any) {
            toast.error("Force Match Failed", { description: err.message });
        }
    };


    return (
        <div className="space-y-6 relative">
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

            <DndContext onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
                {/* Split View */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-[calc(100vh-250px)] min-h-[500px]">

                    {/* Left Column: Bank Feed */}
                    <div className="flex flex-col h-full space-y-4">
                        <div className="flex items-center justify-between flex-shrink-0">
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
                            </div>
                        </div>

                        {/* Zone A: Bank Statement Upload */}
                        <div className="flex-shrink-0">
                            <CompactDropzone
                                key={`bank-${resetKey}`}
                                label="Upload Bank Statement (PDF, CSV, OFX)"
                                docType="BANK_STATEMENT"
                                onUploadSuccess={() => refreshData()}
                            />
                        </div>

                        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden flex-1 flex flex-col">
                            {loadingTx ? (
                                <div className="flex justify-center items-center h-full text-slate-400">Loading transactions...</div>
                            ) : errorTx ? (
                                <div className="flex justify-center items-center h-full text-red-500">Error loading data.</div>
                            ) : bankTransactions.length === 0 ? (
                                <div className="flex justify-center items-center h-full text-slate-400">No transactions found.</div>
                            ) : (
                                <div className="overflow-y-auto flex-1">
                                    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                                        {bankTransactions
                                            .filter(tx => {
                                                if (filter === 'MATCHED') return tx.receipt_id;
                                                if (filter === 'UNLINKED') return !tx.receipt_id;
                                                return true;
                                            })
                                            .map((tx: Transaction) => {
                                                const isMatched = !!tx.receipt_id;
                                                const linkedDoc = isMatched && tx.receipt_id
                                                    ? documents?.find(d => d.id === tx.receipt_id)
                                                    : undefined;

                                                return (
                                                    <DroppableTransaction
                                                        key={tx.id}
                                                        transaction={tx}
                                                        isMatched={isMatched}
                                                        linkedDoc={linkedDoc}
                                                    />
                                                );
                                            })}
                                    </ul>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Column: Receipts Audit */}
                    <div className="flex flex-col h-full space-y-4">
                        <div className="flex items-center justify-between flex-shrink-0">
                            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                                <div className="w-2 h-6 bg-purple-500 rounded-full"></div>
                                Receipts Audit
                                <span className="text-xs font-normal px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded-full text-slate-500">
                                    {receiptDocuments.length} files
                                </span>
                            </h3>
                        </div>

                        {/* Zone B: Receipts Upload */}
                        <div className="flex-shrink-0">
                            <CompactDropzone
                                key={`receipts-${resetKey}`}
                                label="Upload Receipts (PDF, XML, CSV)"
                                docType="RECEIPT"
                                onUploadSuccess={() => refreshData()}
                            />
                        </div>

                        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden flex-1 flex flex-col">
                            {loadingDocs ? (
                                <div className="flex justify-center items-center h-full text-slate-400">Loading documents...</div>
                            ) : errorDocs ? (
                                <div className="flex justify-center items-center h-full text-red-500">Error loading documents.</div>
                            ) : receiptDocuments.length === 0 ? (
                                <div className="flex justify-center items-center h-full text-slate-400">No receipts uploaded.</div>
                            ) : (
                                <div className="overflow-y-auto flex-1 p-2 space-y-2">
                                    {receiptDocuments.map((doc: FinancialDocument) => {
                                        // Strict Linked Logic
                                        const isLinked = bankTransactions.some(bt => bt.receipt_id === doc.id);
                                        return (
                                            <DraggableReceipt
                                                key={doc.id}
                                                doc={doc}
                                                isLinked={isLinked}
                                                onDelete={(id) => deleteMutation.mutate(id)}
                                            />
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>

                </div>
                <DragOverlay>
                    {activeDoc ? (
                        <div className="p-4 bg-white dark:bg-slate-900 rounded-lg shadow-xl border-2 border-purple-500 opacity-90 w-[400px] cursor-grabbing">
                            <div className="flex items-start gap-3">
                                <div className="p-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-purple-600 dark:text-purple-400">
                                    <FileText className="w-5 h-5" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="font-medium text-slate-900 dark:text-slate-100 truncate pr-2">
                                        {activeDoc.original_filename || activeDoc.filename}
                                    </p>
                                    <div className="mt-1 flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
                                        {activeDoc.transactions?.[0] ? (
                                            <>
                                                <span>{formatDate(activeDoc.transactions[0].date)}</span>
                                                <span className="text-slate-300 dark:text-slate-700">•</span>
                                                <span className="font-mono">{formatCurrency(activeDoc.transactions[0].amount)}</span>
                                            </>
                                        ) : (
                                            <span className="italic opacity-70">No specific data</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : null}
                </DragOverlay>
            </DndContext>

            {/* Conflict Resolution Modal */}
            {conflictModalOpen && pendingMatch && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-950 rounded-lg shadow-xl max-w-md w-full overflow-hidden border border-slate-200 dark:border-slate-800 animate-in zoom-in-95 duration-200">
                        <div className="p-6">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="p-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-full text-yellow-600 dark:text-yellow-500">
                                    <AlertTriangle className="w-6 h-6" />
                                </div>
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                                    Discrepancy Detected
                                </h3>
                            </div>

                            <p className="text-slate-600 dark:text-slate-300 mb-6">
                                {pendingMatch.message}
                                <br /><br />
                                <span className="font-medium">Do you want to force this match?</span>
                            </p>

                            <div className="flex justify-end gap-3">
                                <button
                                    onClick={() => {
                                        setConflictModalOpen(false);
                                        setPendingMatch(null);
                                    }}
                                    className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={confirmForceMatch}
                                    className="px-4 py-2 text-sm font-medium text-white bg-yellow-600 hover:bg-yellow-700 rounded-lg"
                                >
                                    Force Match
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
