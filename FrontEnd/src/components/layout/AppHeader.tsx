import { Link, useLocation } from 'react-router-dom';
import { Activity } from 'lucide-react';

export const AppHeader = () => {
  const location = useLocation();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-100 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto max-w-5xl px-6 h-14 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <span className="text-base font-semibold text-slate-900 tracking-tight">CopagoCare AI</span>
        </Link>

        <nav className="flex items-center gap-1">
          <Link
            to="/"
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              location.pathname === '/'
                ? 'bg-blue-50 text-blue-700'
                : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
            }`}
          >
            Paciente
          </Link>
          <Link
            to="/admin"
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              location.pathname === '/admin'
                ? 'bg-blue-50 text-blue-700'
                : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
            }`}
          >
            Administrador
          </Link>
        </nav>
      </div>
    </header>
  );
};
