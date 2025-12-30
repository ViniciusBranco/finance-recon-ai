import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, FileText, Eye, Loader2, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getTaxReports, getTaxReportPreview, getTaxReportDownloadUrl, type TaxReport } from '../lib/api';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

export function History() {
    const navigate = useNavigate();
    const [previewReportId, setPreviewReportId] = useState<string | null>(null);
    const [previewData, setPreviewData] = useState<Record<string, any>[] | null>(null);

    const { data: reports, isLoading, isError, error, refetch } = useQuery<TaxReport[]>({
        queryKey: ['tax-reports'],
        queryFn: getTaxReports,
        retry: 1,
    });

    const handlePreview = async (reportId: string) => {
        setPreviewReportId(reportId);
        setPreviewData(null);
        try {
            const data = await getTaxReportPreview(reportId);
            setPreviewData(data);
        } catch (error) {
            console.error("Preview failed", error);
        }
    };

    const handleClosePreview = () => {
        setPreviewReportId(null);
        setPreviewData(null);
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-black p-4 lg:p-8">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Header */}
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => navigate('/')}
                        className="p-2 hover:bg-white dark:hover:bg-slate-900 rounded-full transition-colors"
                    >
                        <ArrowLeft className="w-6 h-6 text-slate-600 dark:text-slate-400" />
                    </button>
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                            <FileText className="w-7 h-7 text-purple-600" />
                            Histórico de Livros-Caixa
                        </h1>
                        <p className="text-slate-500 dark:text-slate-400">
                            Gerencie e audite os relatórios gerados
                        </p>
                    </div>
                </div>

                {isError ? (
                    <div className="bg-red-50 dark:bg-red-900/10 rounded-xl border border-red-200 dark:border-red-800 p-8 text-center">
                        <Loader2 className="w-10 h-10 text-red-500 mx-auto mb-3" />
                        <h3 className="text-lg font-semibold text-red-700 dark:text-red-400">Erro de Sincronização</h3>
                        <p className="text-red-600 dark:text-red-300 max-w-md mx-auto mb-4">
                            Não foi possível carregar o histórico. {error instanceof Error ? error.message : "Erro desconhecido."}
                        </p>
                        <button
                            onClick={() => refetch()}
                            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
                        >
                            Tentar Novamente
                        </button>
                    </div>
                ) : isLoading ? (
                    <div className="flex justify-center py-20">
                        <Loader2 className="w-8 h-8 animate-spin text-purple-600" />
                    </div>
                ) : !reports || reports.length === 0 ? (
                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-16 text-center shadow-sm">
                        <div className="bg-slate-50 dark:bg-slate-800 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
                            <FileText className="w-10 h-10 text-slate-300 dark:text-slate-600" />
                        </div>
                        <h3 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">Nenhum relatório encontrado</h3>
                        <p className="text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
                            Seus relatórios de Livro-Caixa e auditorias fiscais aparecerão aqui.
                        </p>
                        <button
                            onClick={() => navigate('/')}
                            className="mt-8 px-6 py-2.5 bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-200 text-white dark:text-slate-900 rounded-lg font-medium transition-colors"
                        >
                            Voltar para Dashboard
                        </button>
                    </div>
                ) : (
                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800">
                                    <tr>
                                        <th className="px-6 py-4 font-semibold text-slate-700 dark:text-slate-300">Competência</th>
                                        <th className="px-6 py-4 font-semibold text-slate-700 dark:text-slate-300">Gerado Em</th>
                                        <th className="px-6 py-4 font-semibold text-slate-700 dark:text-slate-300">Total Dedutível</th>
                                        <th className="px-6 py-4 font-semibold text-slate-700 dark:text-slate-300 text-right">Ações</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                    {reports.map((report) => (
                                        <tr key={report.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                                            <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
                                                {format(new Date(report.year, report.month - 1), 'MMMM yyyy', { locale: ptBR })}
                                            </td>
                                            <td className="px-6 py-4 text-slate-600 dark:text-slate-400">
                                                {format(new Date(report.created_at), "dd/MM/yyyy 'às' HH:mm")}
                                            </td>
                                            <td className="px-6 py-4 font-mono text-emerald-600 font-medium">
                                                {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(report.total_deductible)}
                                            </td>
                                            <td className="px-6 py-4 text-right flex justify-end gap-2">
                                                <button
                                                    onClick={() => handlePreview(report.id)}
                                                    className="p-2 text-slate-500 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded-lg transition-colors"
                                                    title="Preview"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </button>
                                                <a
                                                    href={getTaxReportDownloadUrl(report.id)}
                                                    download
                                                    className="p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                                                    title="Download CSV"
                                                >
                                                    <Download className="w-4 h-4" />
                                                </a>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>

            {/* Preview Modal */}
            {previewReportId && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-900 rounded-xl shadow-2xl w-full max-w-4xl max-h-[80vh] flex flex-col border border-slate-200 dark:border-slate-800">
                        <div className="flex items-center justify-between p-4 border-b border-slate-100 dark:border-slate-800">
                            <h3 className="font-semibold text-lg flex items-center gap-2">
                                <Eye className="w-5 h-5 text-slate-500" />
                                Preview (First 10 rows)
                            </h3>
                            <button onClick={handleClosePreview} className="text-slate-500 hover:text-slate-800 dark:hover:text-white">✕</button>
                        </div>
                        <div className="flex-1 overflow-auto p-4 bg-slate-50 dark:bg-black/20">
                            {!previewData || previewData.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-10 h-full text-center">
                                    {previewData === null ? (
                                        <Loader2 className="w-8 h-8 animate-spin text-purple-600" />
                                    ) : (
                                        <>
                                            <FileText className="w-10 h-10 text-slate-300 mb-2" />
                                            <p className="text-slate-500">O arquivo parece estar vazio ou inválido.</p>
                                        </>
                                    )}
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
                                        <table className="w-full text-xs font-mono">
                                            <thead className="bg-slate-100 dark:bg-slate-800">
                                                <tr>
                                                    {Object.keys(previewData[0] || {}).map(key => (
                                                        <th key={key} className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700 uppercase tracking-wider">
                                                            {key}
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-800">
                                                {previewData.map((row, idx) => (
                                                    <tr key={idx}>
                                                        {Object.values(row).map((val: any, i) => (
                                                            <td key={i} className="px-3 py-2 text-slate-700 dark:text-slate-300 whitespace-nowrap">
                                                                {String(val)}
                                                            </td>
                                                        ))}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                    <p className="text-xs text-slate-500 italic text-center">
                                        Showing first {previewData.length} records only.
                                    </p>
                                </div>
                            )}
                        </div>
                        <div className="p-4 border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2 bg-slate-50 dark:bg-slate-900/50 rounded-b-xl">
                            <button
                                onClick={handleClosePreview}
                                className="px-4 py-2 rounded-lg text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-sm font-medium"
                            >
                                Close
                            </button>
                            <a
                                href={getTaxReportDownloadUrl(previewReportId)}
                                download
                                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors text-sm font-medium flex items-center gap-2"
                            >
                                <Download className="w-4 h-4" />
                                Download Full CSV
                            </a>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
