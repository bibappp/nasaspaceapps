import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import Shell from "./components/layout/Shell";
import { Loading } from "./components/ui/ui";
import { AuthProvider, RequireAuth, useAuth } from "./lib/auth";
import { ConfigProvider } from "./lib/config";
import About from "./pages/About";
import Account from "./pages/app/Account";
import Analyses from "./pages/app/Analyses";
import AnalysisView from "./pages/app/AnalysisView";
import Dashboard from "./pages/app/Dashboard";
import FieldEditor from "./pages/app/FieldEditor";
import Fields from "./pages/app/Fields";
import FieldWorkspace from "./pages/app/FieldWorkspace";
import DemoStart from "./pages/auth/DemoStart";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import Landing from "./pages/Landing";
import Methodology from "./pages/Methodology";
import NasaData from "./pages/NasaData";
import Retro from "./pages/Retro";
import Wizard from "./pages/Wizard";

function Private({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}

/** Вошедший пользователь со стартовой страницы сразу попадает на дашборд. */
function Home() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user ? <Navigate to="/app" replace /> : <Landing />;
}

// ключ по id: при переходе между полями рабочее пространство монтируется заново
function FieldWorkspaceKeyed() {
  const { id } = useParams();
  return <FieldWorkspace key={id} />;
}

function LegacyField() {
  return <Navigate to={`/quick${useLocation().search}`} replace />;
}

export default function App() {
  return (
    <ConfigProvider>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/welcome" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/demo" element={<DemoStart />} />

          <Route path="/app" element={<Private><Dashboard /></Private>} />
          <Route path="/app/fields" element={<Private><Fields /></Private>} />
          <Route path="/app/fields/new" element={<Private><FieldEditor /></Private>} />
          <Route path="/app/fields/:id" element={<Private><FieldWorkspaceKeyed /></Private>} />
          <Route path="/app/fields/:id/edit" element={<Private><FieldEditor /></Private>} />
          <Route path="/app/analyses" element={<Private><Analyses /></Private>} />
          <Route path="/app/analyses/:id" element={<Private><AnalysisView /></Private>} />
          <Route path="/app/account" element={<Private><Account /></Private>} />

          <Route path="/nasa" element={<Shell><NasaData /></Shell>} />
          <Route path="/methodology" element={<Shell><Methodology /></Shell>} />
          <Route path="/retro" element={<Shell><Retro /></Shell>} />
          <Route path="/about" element={<Shell><About /></Shell>} />
          <Route path="/quick" element={<Shell><Wizard /></Shell>} />
          {/* совместимость со старыми ссылками */}
          <Route path="/field" element={<LegacyField />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </ConfigProvider>
  );
}
