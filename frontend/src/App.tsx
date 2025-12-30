import { ReconWorkbench } from './components/ReconWorkbench';
import { TaxReportDownload } from './components/TaxReportDownload';
import { History } from './pages/History';
import { Toaster } from 'sonner';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';

function NavLink({ to, children }: { to: string, children: React.ReactNode }) {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Link
      to={to}
      className={`text-sm font-medium transition-colors ${isActive ? 'text-blue-600 dark:text-blue-400 font-bold' : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}`}
    >
      {children}
    </Link>
  );
}

function Dashboard() {
  return (
    <div className="space-y-12">
      {/* Helper/Hero Section */}
      <section className="text-center space-y-4">
        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
          Financial Document Reconciliation
        </h2>
        <p className="max-w-2xl mx-auto text-lg text-slate-600 dark:text-slate-400">
          Automate your accounting by matching bank statements with receipts and invoices.
        </p>
      </section>

      {/* Reports Section */}
      <section className="space-y-4">
        <TaxReportDownload />
      </section>

      {/* Reconciliation Workbench */}
      <section className="space-y-6 pt-4">
        <ReconWorkbench />
      </section>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans pb-20">
        <Toaster position="top-right" richColors />
        {/* Header */}
        <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 sticky top-0 z-10 transition-colors shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-md">
                <span className="text-white font-bold text-lg">R</span>
              </div>
              <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">
                Finance Recon AI
              </h1>
            </Link>
            <nav className="flex gap-6">
              <NavLink to="/">Dashboard</NavLink>
              <NavLink to="/history">History</NavLink>
              <button className="text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors">
                Settings
              </button>
            </nav>
          </div>
        </header>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="border-t border-slate-200 dark:border-slate-800 mt-12 py-8 text-center text-sm text-slate-500">
          © 2025 Finance Recon AI. All rights reserved.
        </footer>
      </div>
    </BrowserRouter>
  )
}

export default App
