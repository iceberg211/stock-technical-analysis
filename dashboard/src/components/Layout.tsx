import { NavLink, Outlet } from 'react-router-dom';
import { TrendingUp, BarChart3, MessageSquare } from 'lucide-react';

const nav = [
  { to: '/', icon: TrendingUp, label: '交易信号' },
  { to: '/backtests', icon: BarChart3, label: '回测报告' },
  { to: '/conversations', icon: MessageSquare, label: '分析对话' },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col fixed h-screen">
        <div className="p-5 border-b border-gray-100">
          <h1 className="text-sm font-semibold text-gray-900 tracking-tight">Trading Copilot</h1>
          <p className="text-xs text-gray-400 mt-0.5">AI 交易研究助手</p>
        </div>
        <nav className="flex-1 p-2">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-gray-100 text-xs text-gray-400">
          v0.1.0
        </div>
      </aside>
      <main className="flex-1 ml-56">
        <Outlet />
      </main>
    </div>
  );
}
