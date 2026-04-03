import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  ShieldCheck,
  Pencil,
  FlaskConical,
  ScrollText,
  GitBranch,
} from "lucide-react";
import { clsx } from "clsx";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/rules", icon: ShieldCheck, label: "Rules" },
  { to: "/builder", icon: Pencil, label: "Rule Builder" },
  { to: "/playground", icon: FlaskConical, label: "Playground" },
  { to: "/audit", icon: ScrollText, label: "Audit Trail" },
  { to: "/graph", icon: GitBranch, label: "Rule Graph" },
] as const;

export function Layout() {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-gray-200 bg-white">
        <div className="flex h-16 items-center gap-3 border-b border-gray-200 px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white font-bold text-sm">
            AC
          </div>
          <div>
            <h1 className="text-sm font-semibold text-gray-900">ACGS</h1>
            <p className="text-[11px] text-gray-500">Governance Dashboard</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-gray-200 px-6 py-4">
          <p className="text-[11px] text-gray-400">Constitutional Hash</p>
          <code className="text-[11px] font-mono text-gray-500">608508a9bd224290</code>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-64 flex-1 p-8">
        <Outlet />
      </main>
    </div>
  );
}
