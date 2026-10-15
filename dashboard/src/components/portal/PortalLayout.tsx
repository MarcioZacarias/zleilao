import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ChevronDown, Gavel, Home, LogOut, Menu, Search, ShieldCheck, User, X } from "lucide-react";
import { useBranding } from "../../hooks/useBranding";
import { useAuth } from "../../context/AuthContext";
import { SearchBar } from "./SearchBar";

const NAV = [
  { to: "/", label: "Início", icon: Home, end: true },
  { to: "/busca", label: "Buscar lotes", icon: Search, end: false },
  { to: "/busca?status=auction_soon&sort=session_asc", label: "Pregões em breve", icon: Gavel, end: false },
];

/** Menu da conta no cabeçalho (desktop). */
function UserMenu({ name, isAdmin, onLogout }: { name: string; isAdmin: boolean; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative ml-2" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex max-w-[190px] items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-radar-text hover:border-white/20 hover:bg-white/5"
      >
        <User size={15} className="shrink-0 text-radar-muted" />
        <span className="truncate">{name}</span>
        <ChevronDown size={14} className={`shrink-0 text-radar-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-52 overflow-hidden rounded-xl border border-radar-border bg-radar-surface py-1 shadow-lift"
        >
          <Link
            to="/conta"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2.5 text-sm text-radar-text hover:bg-white/5"
          >
            <User size={15} className="text-radar-muted" /> Minha conta
          </Link>
          {isAdmin && (
            <Link
              to="/admin"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2.5 text-sm text-radar-text hover:bg-white/5"
            >
              <ShieldCheck size={15} className="text-radar-muted" /> Admin
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="flex w-full items-center gap-2 border-t border-radar-border px-3 py-2.5 text-left text-sm text-radar-muted hover:bg-white/5 hover:text-radar-text"
          >
            <LogOut size={15} /> Sair
          </button>
        </div>
      )}
    </div>
  );
}

export default function PortalLayout() {
  const branding = useBranding();
  const { token, user, isAdmin, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const isHome = location.pathname === "/";

  const displayName = user?.name || user?.email || "Minha conta";
  const logged = !!token && !!user;

  const handleLogout = () => {
    logout();
    setOpen(false);
    navigate("/");
  };

  return (
    <div className="portal flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-radar-border bg-radar-bg/85 backdrop-blur supports-[backdrop-filter]:bg-radar-bg/70">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6 md:h-20">
          <Link to="/" className="flex shrink-0 items-center gap-2" aria-label={branding.site_title}>
            <img src={branding.logo_dark} alt={branding.site_title} className="h-12 w-auto object-contain md:h-16" />
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

            {logged ? (
              <UserMenu name={displayName} isAdmin={isAdmin} onLogout={handleLogout} />
            ) : (
              <Link
                to="/entrar"
                className="ml-2 inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-radar-muted hover:border-white/20 hover:text-radar-text"
              >
                <User size={15} /> Entrar
              </Link>
            )}
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

              <div className="my-2 border-t border-radar-border" />

              {logged ? (
                <>
                  <div className="px-3 py-1 text-xs uppercase tracking-wider text-radar-muted">{displayName}</div>
                  <Link
                    to="/conta"
                    onClick={() => setOpen(false)}
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-radar-text hover:bg-white/5"
                  >
                    <User size={16} className="text-radar-muted" /> Minha conta
                  </Link>
                  {isAdmin && (
                    <Link
                      to="/admin"
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-radar-text hover:bg-white/5"
                    >
                      <ShieldCheck size={16} className="text-radar-muted" /> Admin
                    </Link>
                  )}
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-radar-muted hover:bg-white/5 hover:text-radar-text"
                  >
                    <LogOut size={16} /> Sair
                  </button>
                </>
              ) : (
                <Link
                  to="/entrar"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-radar-text hover:bg-white/5"
                >
                  <User size={16} className="text-radar-muted" /> Entrar
                </Link>
              )}
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
              <img src={branding.logo_dark} alt={branding.site_title} className="h-16 w-auto object-contain" />
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
                <h4 className="mb-2 font-semibold text-radar-text">Sua conta</h4>
                <ul className="space-y-1 text-radar-muted">
                  {logged ? (
                    <>
                      <li><Link to="/conta?aba=alertas" className="hover:text-radar-text">Meus alertas</Link></li>
                      <li><Link to="/conta?aba=filtros" className="hover:text-radar-text">Filtros salvos</Link></li>
                      <li><Link to="/conta?aba=plano" className="hover:text-radar-text">Plano</Link></li>
                    </>
                  ) : (
                    <>
                      <li><Link to="/entrar" className="hover:text-radar-text">Entrar</Link></li>
                      <li><Link to="/cadastro" className="hover:text-radar-text">Criar conta</Link></li>
                      <li className="text-radar-muted/70">Alertas de lotes novos</li>
                    </>
                  )}
                </ul>
              </div>
              <div>
                <h4 className="mb-2 font-semibold text-radar-text">Transparência</h4>
                <ul className="space-y-1 text-radar-muted">
                  <li>Fonte e última coleta em todo lote</li>
                  <li>Lances só no site oficial</li>
                  <li>Dados pessoais mascarados</li>
                  {/* Exigência da LGPD e condição do AdSense: as duas páginas
                      precisam estar alcançáveis de qualquer tela. */}
                  <li>
                    <Link to="/privacidade" className="hover:text-radar-text">
                      Política de privacidade
                    </Link>
                  </li>
                  <li>
                    <Link to="/termos" className="hover:text-radar-text">
                      Termos de uso
                    </Link>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          {branding.disclaimer && (
            <p className="mt-8 border-t border-radar-border pt-4 text-xs leading-relaxed text-radar-muted/80">
              {branding.disclaimer}
            </p>
          )}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-radar-muted/60">
            <p>
              © {new Date().getFullYear()} {branding.site_title}. Agregador independente — não realizamos leilões nem intermediamos lances.
            </p>
            {/* Porta de serviço: discreta, sem disputar espaço com a conta do assinante. */}
            <Link to={isAdmin ? "/admin" : "/login"} className="hover:text-radar-muted">
              Área administrativa
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
