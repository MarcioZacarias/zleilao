import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Menu, X, Search, Home, Gavel, ShieldCheck } from "lucide-react";
import { useBranding } from "../../hooks/useBranding";
import { useAuth } from "../../context/AuthContext";
import { SearchBar } from "./SearchBar";

const NAV = [
  { to: "/", label: "Início", icon: Home, end: true },
  { to: "/busca", label: "Buscar lotes", icon: Search, end: false },
  { to: "/busca?status=auction_soon&sort=session_asc", label: "Pregões em breve", icon: Gavel, end: false },
];

export default function PortalLayout() {
  const branding = useBranding();
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <div className="portal flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-radar-border bg-radar-bg/85 backdrop-blur supports-[backdrop-filter]:bg-radar-bg/70">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-2" aria-label={branding.site_title}>
            <img src={branding.logo_dark} alt={branding.site_title} className="h-9 w-auto object-contain" />
          </Link>

          {!isHome && (
            <div className="hidden flex-1 md:block md:max-w-xl">
              <SearchBar key={location.search} initial={new URLSearchParams(location.search).get("q") ?? ""} />
            </div>
          )}

          <nav className="ml-auto hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-sm transition-colors ${
                    isActive && (n.end || !n.to.includes("?"))
                      ? "bg-white/5 text-radar-text"
                      : "text-radar-muted hover:bg-white/5 hover:text-radar-text"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
            <Link
              to={token ? "/admin" : "/login"}
              className="ml-2 inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-radar-muted hover:border-white/20 hover:text-radar-text"
            >
              <ShieldCheck size={15} /> Admin
            </Link>
          </nav>

          <button
            onClick={() => setOpen((o) => !o)}
            className="ml-auto rounded-lg p-2 text-radar-muted hover:bg-white/5 md:hidden"
            aria-label="Abrir menu"
            aria-expanded={open}
          >
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>

        {open && (
          <div className="border-t border-radar-border bg-radar-surface md:hidden">
            <div className="space-y-1 px-4 py-3">
              {!isHome && <SearchBar className="mb-2" />}
              {NAV.map((n) => (
                <Link
                  key={n.to}
                  to={n.to}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-radar-text hover:bg-white/5"
                >
                  <n.icon size={16} className="text-radar-muted" /> {n.label}
                </Link>
              ))}
              <Link
                to={token ? "/admin" : "/login"}
                onClick={() => setOpen(false)}
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-radar-muted hover:bg-white/5"
              >
                <ShieldCheck size={16} /> Admin
              </Link>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="mt-12 border-t border-radar-border">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-md">
              <img src={branding.logo_dark} alt={branding.site_title} className="h-8 w-auto object-contain" />
              {branding.tagline && <p className="mt-3 text-sm text-radar-muted">{branding.tagline}</p>}
            </div>
            <div className="grid grid-cols-2 gap-6 text-sm sm:grid-cols-3">
              <div>
                <h4 className="mb-2 font-semibold text-radar-text">Navegar</h4>
                <ul className="space-y-1 text-radar-muted">
                  <li><Link to="/" className="hover:text-radar-text">Início</Link></li>
                  <li><Link to="/busca" className="hover:text-radar-text">Buscar lotes</Link></li>
                  <li><Link to="/busca?status=auction_soon&sort=session_asc" className="hover:text-radar-text">Pregões em breve</Link></li>
                </ul>
              </div>
              <div>
                <h4 className="mb-2 font-semibold text-radar-text">Transparência</h4>
                <ul className="space-y-1 text-radar-muted">
                  <li>Fonte e última coleta em todo lote</li>
                  <li>Lances só no site oficial</li>
                  <li>Dados pessoais mascarados</li>
                </ul>
              </div>
              <div>
                <h4 className="mb-2 font-semibold text-radar-text">Sistema</h4>
                <ul className="space-y-1 text-radar-muted">
                  <li><Link to="/login" className="hover:text-radar-text">Área administrativa</Link></li>
                </ul>
              </div>
            </div>
          </div>
          {branding.disclaimer && (
            <p className="mt-8 border-t border-radar-border pt-4 text-xs leading-relaxed text-radar-muted/80">
              {branding.disclaimer}
            </p>
          )}
          <p className="mt-4 text-xs text-radar-muted/60">
            © {new Date().getFullYear()} {branding.site_title}. Agregador independente — não realizamos leilões nem intermediamos lances.
          </p>
        </div>
      </footer>
    </div>
  );
}
