import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { updateTaxAnalysis, analyzeIndividual } from '../lib/api';
import type { TaxAnalysis } from '../lib/api';
import { CheckCircle2, AlertTriangle, XCircle, Edit2, Save, X, BookOpen, Scale, PlayCircle, Loader2, Copy, CheckSquare } from 'lucide-react';
import { toast } from 'sonner';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import ReactMarkdown from 'react-markdown';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

interface TaxAnalysisPanelProps {
    transactionId: string;
    analysis?: TaxAnalysis | null;
    onClose?: () => void;
}

export const TaxAnalysisPanel: React.FC<TaxAnalysisPanelProps> = ({ transactionId, analysis: initialAnalysis, onClose }) => {
    const queryClient = useQueryClient();
    const [isEditing, setIsEditing] = useState(false);
    const [isAnalyzing, setIsAnalyzing] = useState(false);

    // Edit State
    const [editForm, setEditForm] = useState({
        classification: initialAnalysis?.classification || 'Não Dedutível',
        category: initialAnalysis?.category || '',
        month: initialAnalysis?.month || '',
        justification_text: initialAnalysis?.justification_text || '',
        legal_citation: initialAnalysis?.legal_citation || ''
    });

    // Mutations
    const runAnalysisMutation = useMutation({
        mutationFn: analyzeIndividual,
        onMutate: () => setIsAnalyzing(true),
        onSuccess: () => {
            toast.success("Tax Analysis Complete");
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
        },
        onError: (err: any) => {
            toast.error("Analysis Failed", { description: err.message });
        },
        onSettled: () => setIsAnalyzing(false)
    });

    const updateMutation = useMutation({
        mutationFn: (data: typeof editForm) => updateTaxAnalysis(transactionId, data),
        onSuccess: () => {
            toast.success("Tax Analysis Updated");
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
            setIsEditing(false);
        },
        onError: (err: any) => {
            toast.error("Update Failed", { description: err.message });
        }
    });

    const handleSave = () => {
        updateMutation.mutate(editForm);
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        toast.success("Copied to clipboard");
    };

    if (!initialAnalysis && !isAnalyzing) {
        return (
            <div className="p-4 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 flex flex-col items-center gap-3 text-center">
                <BookOpen className="w-10 h-10 text-slate-300 dark:text-slate-600" />
                <p className="text-sm text-slate-500">No tax analysis available for this transaction.</p>
                <button
                    onClick={() => runAnalysisMutation.mutate(transactionId)}
                    disabled={isAnalyzing}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                    {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                    Run AI Analysis
                </button>
            </div>
        );
    }

    if (isAnalyzing) {
        return (
            <div className="p-8 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 flex flex-col items-center gap-4 text-center animate-pulse">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                <p className="text-sm text-slate-600 dark:text-slate-300 font-medium">Consulting Tax Knowledge Base...</p>
                <p className="text-xs text-slate-400">Verifying deductibility and legal citations.</p>
            </div>
        );
    }

    const analysis = initialAnalysis!; // We know it exists here

    const getClassificationColor = (cls: string) => {
        const lower = cls.toLowerCase();
        if (lower.includes('dedutível') && !lower.includes('não')) return "text-emerald-600 bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800 dark:text-emerald-400";
        if (lower.includes('parcial')) return "text-yellow-600 bg-yellow-50 border-yellow-200 dark:bg-yellow-900/20 dark:border-yellow-800 dark:text-yellow-400";
        return "text-slate-600 bg-slate-50 border-slate-200 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400"; // Não dedutível as gray/neutral
    };

    const getClassificationIcon = (cls: string) => {
        const lower = cls.toLowerCase();
        if (lower.includes('dedutível') && !lower.includes('não')) return <CheckCircle2 className="w-4 h-4" />;
        if (lower.includes('parcial')) return <AlertTriangle className="w-4 h-4" />;
        return <XCircle className="w-4 h-4" />;
    };

    const getRiskColor = (risk?: string | null) => {
        const r = (risk || '').toLowerCase();
        if (r === 'baixo') return "text-emerald-600 dark:text-emerald-400";
        if (r === 'médio' || r === 'medio') return "text-yellow-600 dark:text-yellow-400";
        if (r === 'alto') return "text-red-600 dark:text-red-400";
        return "text-slate-500";
    };

    // Extract checklist from raw_analysis or fallback to parsing justification (less reliable)
    const checklistItems = analysis.raw_analysis?.checklist || [];
    // If raw_analysis is empty (legacy data), we might show full justification.
    // Ideally we prefer raw_analysis.comentario as the clean justification.
    const justificationDisplay = analysis.raw_analysis?.comentario || analysis.justification_text || "Sem justificativa.";

    if (isEditing) {
        return (
            <div className="bg-white dark:bg-slate-950 rounded-lg border border-blue-200 dark:border-blue-900 shadow-sm p-4 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                    <h4 className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                        <Edit2 className="w-4 h-4 text-blue-500" />
                        Edit Tax Analysis
                    </h4>
                    <button onClick={() => setIsEditing(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="col-span-2">
                        <label className="block text-xs font-medium text-slate-500 mb-1">Classification</label>
                        <select
                            value={editForm.classification}
                            onChange={e => setEditForm(prev => ({ ...prev, classification: e.target.value }))}
                            className="w-full text-sm rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                        >
                            <option value="Dedutível">Dedutível</option>
                            <option value="Parcialmente Dedutível">Parcialmente Dedutível</option>
                            <option value="Não Dedutível">Não Dedutível</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Category (Livro Caixa)</label>
                        <input
                            type="text"
                            value={editForm.category}
                            onChange={e => setEditForm(prev => ({ ...prev, category: e.target.value }))}
                            className="w-full text-sm rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-slate-500 mb-1">Month (Ref)</label>
                        <input
                            type="text"
                            value={editForm.month}
                            onChange={e => setEditForm(prev => ({ ...prev, month: e.target.value }))}
                            className="w-full text-sm rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                            placeholder="MM/YYYY"
                        />
                    </div>

                    <div className="col-span-2">
                        <label className="block text-xs font-medium text-slate-500 mb-1">Legal Citation</label>
                        <input
                            type="text"
                            value={editForm.legal_citation}
                            onChange={e => setEditForm(prev => ({ ...prev, legal_citation: e.target.value }))}
                            className="w-full text-sm rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono text-xs"
                            placeholder="e.g. Art. 4, Lei 9250"
                        />
                    </div>

                    <div className="col-span-2">
                        <label className="block text-xs font-medium text-slate-500 mb-1">Justification</label>
                        <textarea
                            value={editForm.justification_text}
                            onChange={e => setEditForm(prev => ({ ...prev, justification_text: e.target.value }))}
                            className="w-full text-sm rounded-md border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 h-24 resize-none"
                        />
                    </div>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                    <button
                        onClick={() => setIsEditing(false)}
                        className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-md"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={updateMutation.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md"
                    >
                        {updateMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                        Save Changes
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden relative group/panel">
            {/* Header / Banner */}
            <div className="flex items-center justify-between p-3 bg-slate-50/50 dark:bg-slate-900/50 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-3">
                    <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border shadow-sm", getClassificationColor(analysis.classification))}>
                        {getClassificationIcon(analysis.classification)}
                        {analysis.classification}
                    </div>
                    {analysis.risk_level && (
                        <div className="flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                            <span className="text-slate-500 dark:text-slate-400">Risco:</span>
                            <span className={cn(getRiskColor(analysis.risk_level))}>{analysis.risk_level}</span>
                        </div>
                    )}
                    {analysis.is_manual_override && (
                        <span className="text-[10px] uppercase font-bold text-slate-400 border border-slate-200 px-1.5 py-0.5 rounded">Manual</span>
                    )}
                </div>

                <div className="flex items-center gap-1">
                    <button
                        onClick={() => setIsEditing(true)}
                        className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                        title="Edit Analysis"
                    >
                        <Edit2 className="w-4 h-4" />
                    </button>
                    {onClose && (
                        <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-md">
                            <X className="w-4 h-4" />
                        </button>
                    )}
                </div>
            </div>

            <div className="p-4 space-y-4">
                {/* Meta Grid */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span className="block text-xs text-slate-500 mb-0.5">Category</span>
                        <span className="font-medium text-slate-800 dark:text-slate-200">{analysis.category || '-'}</span>
                    </div>
                    <div>
                        <span className="block text-xs text-slate-500 mb-0.5">Competência</span>
                        <span className="font-medium text-slate-800 dark:text-slate-200">{analysis.month || '-'}</span>
                    </div>
                </div>

                {/* Legal Justification Box */}
                <div className="bg-slate-50 dark:bg-slate-900/50 rounded-md border border-slate-200 dark:border-slate-800 overflow-hidden">
                    <div className="px-3 py-2 bg-slate-100/50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Scale className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                            <h5 className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">Justificativa Legal</h5>
                        </div>
                        <button
                            onClick={() => copyToClipboard(justificationDisplay)}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                            title="Copy Justification"
                        >
                            <Copy className="w-3.5 h-3.5" />
                        </button>
                    </div>

                    <div className="p-3">
                        <div className="text-sm text-slate-600 dark:text-slate-400 prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-headings:my-2">
                            <ReactMarkdown>{justificationDisplay}</ReactMarkdown>
                        </div>
                    </div>
                </div>

                {/* Checklist Section */}
                {checklistItems.length > 0 && (
                    <div className="space-y-2">
                        <div className="flex items-center gap-2">
                            <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                            <h5 className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">Checklist de Comprovação</h5>
                        </div>
                        <ul className="space-y-1">
                            {checklistItems.map((item, idx) => (
                                <li key={idx} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400">
                                    <div className="mt-1.5 w-1 h-1 rounded-full bg-blue-400 flex-shrink-0" />
                                    <span>{item}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {analysis.legal_citation && (
                    <div className="flex items-start gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                        <BookOpen className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
                        <div>
                            <span className="block text-xs font-semibold text-slate-500 mb-0.5">Citação Legal Base</span>
                            <span className="text-sm font-medium text-slate-700 dark:text-slate-300 italic">
                                {analysis.legal_citation}
                            </span>
                        </div>
                    </div>
                )}

            </div>
        </div>
    );
};
