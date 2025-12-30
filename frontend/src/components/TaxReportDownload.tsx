import { useState, useEffect } from 'react';
import axios from 'axios';
import { Download, FileText, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getTransactions, generateTaxReport, type Transaction } from '../lib/api';

export function TaxReportDownload() {
    // State
    const [month, setMonth] = useState(new Date().getMonth() + 1);
    const [year, setYear] = useState(new Date().getFullYear());
    const [isLoading, setIsLoading] = useState(false);
    const navigate = useNavigate();





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
            await generateTaxReport(month, year);
            toast.success('Relatório gerado com sucesso!');
            navigate('/history');
        } catch (error) {
            console.error('Generation failed', error);
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
