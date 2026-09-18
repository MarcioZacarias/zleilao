import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Radio,
  FolderTree,
  Package,
  ClipboardCheck,
  AlertTriangle,
  Copy,
  Timer,
  Settings,
  LogOut,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useBranding } from "../hooks/useBranding";

const links = [
  { to: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { to: "/admin/fontes", label: "Fontes", icon: Radio },
  { to: "/admin/categorias", label: "Categorias", icon: FolderTree },
  { to: "/admin/itens", label: "Itens", icon: Package },
  { to: "/admin/revisao", label: "Revisão", icon: ClipboardCheck },
  { to: "/admin/incidentes", label: "Incidentes", icon: AlertTriangle },
  { to: "/admin/duplicados", label: "Duplicados", icon: Copy },
  { to: "/admin/jobs", label: "Jobs", icon: Timer },
  { to: "/admin/configuracoes", label: "Configurações", icon: Settings },
];

interface SidebarProps {
  onClose?: () => void;
}

export default function Sidebar({ onClose }: SidebarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const branding = useBranding();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside className="flex min-h-screen w-64 flex-col bg-gray-900 text-white">
      <div className="flex items-center justify-between gap-3 border-b border-gray-800 p-4">
        <img src={branding.logo_dark} alt={branding.site_title} className="h-12 w-auto object-contain" />
        {onClose && (
          <button onClick={onClose} className="rounded-lg p-1 transition-colors hover:bg-gray-800 lg:hidden" aria-label="Fechar menu">
            <X size={18} className="text-gray-400" />
          </button>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto py-4">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === "/admin"}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-6 py-3 text-sm transition-colors ${
                isActive ? "bg-primary-600 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <link.icon size={18} />
            {link.label}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-3 border-t border-gray-800 p-4">
        <a
          href="/"
          target="_blank"
          rel="noopener noreferrer"
          className="block text-xs text-gray-500 transition-colors hover:text-gray-300"
        >
          Ver portal público
        </a>
        {user && (
          <div className="flex items-center justify-between">
            <span className="max-w-[160px] truncate text-xs text-gray-500" title={user.email}>
              {user.name || user.email}
            </span>
            <button onClick={handleLogout} className="text-gray-500 transition-colors hover:text-red-400" title="Sair">
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
