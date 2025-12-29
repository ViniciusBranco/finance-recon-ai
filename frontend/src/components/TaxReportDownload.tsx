import { useState, useEffect } from 'react';
import axios from 'axios';
import { Download, FileText, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import { getTransactions, type Transaction } from '../lib/api';

export function TaxReportDownload() {
    const [month, setMonth] = useState(new Date().getMonth() + 1);
    const [year, setYear] = useState(new Date().getFullYear());
    const [isLoading, setIsLoading] = useState(false);
    const [isBatchLoading, setIsBatchLoading] = useState(false);
    const [quota, setQuota] = useState<{ used: number; limit: number; remaining: number } | null>(null);

    const getApiUrl = () => {
        // @ts-ignore
        const envUrl = import.meta.env.VITE_API_URL;
        return envUrl || 'http://localhost:8000';
    };

    useEffect(() => {
        fetchQuota();
    }, []);

    const fetchQuota = async () => {
        try {
            const res = await axios.get(`${getApiUrl()}/api/v1/tax/quota-status`);
            setQuota(res.data);
        } catch (e) {
            console.error("Failed to fetch quota", e);
        }
    };

    const handleBatchAnalyze = async () => {
        setIsBatchLoading(true);
        try {
            const res = await axios.post(`${getApiUrl()}/api/v1/tax-analysis/batch`);
            toast.success(res.data.message);
            fetchQuota(); // Refresh quota
        } catch (error) {
            toast.error("Erro na análise em lote.");
        } finally {
            setIsBatchLoading(false);
        }
    };

    // Generate Year Options (CurrentYear - 2 to CurrentYear + 1)
    const currentYear = new Date().getFullYear();
    const years = Array.from({ length: 4 }, (_, i) => currentYear - 2 + i);

    const months = [
        { value: 1, label: 'Janeiro' },
        { value: 2, label: 'Fevereiro' },
        { value: 3, label: 'Março' },
        { value: 4, label: 'Abril' },
        { value: 5, label: 'Maio' },
        { value: 6, label: 'Junho' },
        { value: 7, label: 'Julho' },
        { value: 8, label: 'Agosto' },
        { value: 9, label: 'Setembro' },
        { value: 10, label: 'Outubro' },
        { value: 11, label: 'Novembro' },
        { value: 12, label: 'Dezembro' },
    ];

    // Data-Aware Logic
    const { data: transactions } = useQuery<Transaction[]>({
        queryKey: ['transactions', 'BANK_STATEMENT'],
        queryFn: () => getTransactions(false, 'BANK_STATEMENT'),
        staleTime: 1000 * 60 * 5 // 5 min cache
    });

    const monthsWithData = new Set<number>();
    if (transactions) {
        transactions.forEach(tx => {
            if (tx.tax_analysis?.classification?.toLowerCase().includes('dedutível') && !tx.tax_analysis?.classification?.toLowerCase().includes('não')) {
                // Parse date YYYY-MM-DD
                const date = new Date(tx.date);
                if (date.getFullYear() === year) {
                    monthsWithData.add(date.getMonth() + 1);
                }
            }
        });
    }

    // Auto-select latest month with data on mount/data load
    useEffect(() => {
        if (monthsWithData.size > 0 && !monthsWithData.has(month)) {
            // Find latest
            const sorted = Array.from(monthsWithData).sort((a, b) => b - a);
            if (sorted.length > 0) {
                setMonth(sorted[0]);
            }
        }
        // Run only once when data first loads or year changes implies re-calc
        // We add strict dependency to avoid loops, but we want it to behave "smartly"
    }, [year, transactions]); // When transactions load, we check.


    const handleDownload = async () => {
        setIsLoading(true);
        try {
            const getApiUrl = () => {
                // @ts-ignore
                const envUrl = import.meta.env.VITE_API_URL;
                return envUrl || 'http://localhost:8000';
            };

            const response = await axios.get(`${getApiUrl()}/api/v1/tax/report/livro-caixa`, {
                params: { month, year },
                responseType: 'blob',
            });

            // Create blob link to download
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;

            // Extract filename from header or default
            const contentDisposition = response.headers['content-disposition'];
            let filename = `tax_report_${month.toString().padStart(2, '0')}_${year}.csv`;
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                if (filenameMatch && filenameMatch.length === 2)
                    filename = filenameMatch[1];
            }

            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();

            // Cleanup
            link.remove();
            window.URL.revokeObjectURL(url);

            toast.success('Relatório baixado com sucesso!');
        } catch (error) {
            console.error('Download failed', error);
            if (axios.isAxiosError(error) && error.response?.status === 404) {
                toast.error('Sem dados para este período', {
                    description: `Não foram encontradas despesas dedutíveis para ${months.find(m => m.value === month)?.label}/${year}. Verifique se as transações foram analisadas.`
                });
            } else {
                toast.error('Erro ao gerar o relatório. Tente novamente.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
            <div className="flex items-start justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                        <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Relatório Livro-Caixa</h3>
                            {quota && (
                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${quota.remaining > 0
                                    ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800'
                                    : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800'
                                    }`}>
                                    Quota Diária: {quota.used} / {quota.limit}
                                </span>
                            )}
                        </div>
                        <p className="text-sm text-slate-500 dark:text-slate-400">Gere o arquivo CSV compatível com o Carnê-Leão e analise pendências.</p>
                    </div>
                </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 items-end">
                <div className="w-full sm:w-40">
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Mês</label>
                    <select
                        value={month}
                        onChange={(e) => setMonth(Number(e.target.value))}
                        className="w-full rounded-lg border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white sm:text-sm focus:ring-blue-500 focus:border-blue-500 p-2.5"
                    >
                        {months.map((m) => (
                            <option key={m.value} value={m.value}>
                                {m.label} {monthsWithData.has(m.value) ? ' •' : ''}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="w-full sm:w-32">
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Ano</label>
                    <select
                        value={year}
                        onChange={(e) => setYear(Number(e.target.value))}
                        className="w-full rounded-lg border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white sm:text-sm focus:ring-blue-500 focus:border-blue-500 p-2.5"
                    >
                        {years.map((y) => (
                            <option key={y} value={y}>{y}</option>
                        ))}
                    </select>
                </div>

                <button
                    onClick={handleBatchAnalyze}
                    disabled={isBatchLoading || (quota?.remaining !== undefined && quota.remaining <= 0)}
                    className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm shadow-purple-500/20"
                >
                    {isBatchLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                    {isBatchLoading ? 'Processando (13s/item)...' : 'Analisar Pendentes'}
                </button>

                <button
                    onClick={handleDownload}
                    disabled={isLoading}
                    className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm shadow-blue-500/20"
                >
                    {isLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Download className="w-4 h-4" />
                    )}
                    {isLoading ? 'Gerando...' : 'Gerar Livro-Caixa (CSV)'}
                </button>
            </div>
        </div>
    );
}
