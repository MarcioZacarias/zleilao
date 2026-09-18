import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { useApplyBranding } from "./hooks/useBranding";
import PortalLayout from "./components/portal/PortalLayout";
import Home from "./pages/portal/Home";
import Search from "./pages/portal/Search";
import LotDetail from "./pages/portal/LotDetail";
import AuctionPage from "./pages/portal/AuctionPage";
import NotFound from "./pages/portal/NotFound";

// O admin (e a biblioteca de graficos que so ele usa) carrega sob demanda.
// Sem isso, quem abre a vitrine no celular baixa o painel inteiro junto.
const Layout = lazy(() => import("./components/Layout"));
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/admin/Dashboard"));
const Sources = lazy(() => import("./pages/admin/Sources"));
const Categories = lazy(() => import("./pages/admin/Categories"));
const Items = lazy(() => import("./pages/admin/Items"));
const Review = lazy(() => import("./pages/admin/Review"));
const Incidents = lazy(() => import("./pages/admin/Incidents"));
const Duplicates = lazy(() => import("./pages/admin/Duplicates"));
const Jobs = lazy(() => import("./pages/admin/Jobs"));
const Settings = lazy(() => import("./pages/admin/Settings"));

function Loading() {
  return <div className="flex min-h-screen items-center justify-center bg-gray-50 text-gray-400">Carregando...</div>;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <Loading />;
  }

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}

export default function App() {
  useApplyBranding();
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {/* Portal público */}
        <Route element={<PortalLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/busca" element={<Search />} />
          <Route path="/lote/:id" element={<LotDetail />} />
          <Route path="/pregao/:id" element={<AuctionPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>

        <Route path="/login" element={<Login />} />

        {/* Admin protegido */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="fontes" element={<Sources />} />
          <Route path="categorias" element={<Categories />} />
          <Route path="itens" element={<Items />} />
          <Route path="revisao" element={<Review />} />
          <Route path="incidentes" element={<Incidents />} />
          <Route path="duplicados" element={<Duplicates />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="configuracoes" element={<Settings />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
