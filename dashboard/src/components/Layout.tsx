import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, TrendingUp, BarChart3, PieChart } from 'lucide-react';

const nav = [
  { to: '/', icon: LayoutDashboard, label: '总览' },
  { to: '/signals', icon: TrendingUp, label: '交易信号' },
  { to: '/backtests', icon: BarChart3, label: '回测报告' },
  { to: '/review', icon: PieChart, label: '复盘统计' },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#0B1120] flex">
      {/* Sidebar */}
      <aside className="w-60 bg-[#0f1629] border-r border-gray-800/60 flex flex-col fixed h-screen">
        <div className="px-5 py-5 border-b border-gray-800/60">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
              <TrendingUp size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-gray-100 tracking-tight">Trading Copilot</h1>
              <p className="text-[11px] text-gray-500">AI Signal Dashboard</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50 border border-transparent'
                }`
              }
            >
              <Icon size={18} strokeWidth={1.8} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-gray-800/60">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] text-gray-500">v0.2.0</span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 ml-60 min-h-screen">
        <Outlet />
      </main>
    </div>
  );
}
