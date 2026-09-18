import { useState } from "react";
import { Outlet, Link } from "react-router-dom";
import { Menu, ExternalLink } from "lucide-react";
import Sidebar from "./Sidebar";
import { useBranding } from "../hooks/useBranding";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const branding = useBranding();

  return (
    <div className="flex min-h-screen bg-gray-50">
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      <div
        className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-in-out lg:relative lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      <main className="min-w-0 flex-1 overflow-auto">
        <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-1.5 transition-colors hover:bg-gray-100 lg:hidden"
            aria-label="Abrir menu"
          >
            <Menu size={20} className="text-gray-600" />
          </button>
          <span className="font-semibold text-gray-900 lg:hidden">{branding.site_title}</span>
          <span className="hidden text-sm text-gray-500 lg:inline">Painel administrativo</span>
          <Link
            to="/"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600"
          >
            Ver portal <ExternalLink size={12} />
          </Link>
        </div>

        <div className="p-4 md:p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
