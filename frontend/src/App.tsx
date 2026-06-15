import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { AuditPage } from "./pages/AuditPage";
import { RulesPage } from "./pages/RulesPage";
import { AdminPage } from "./pages/AdminPage";
import { can, type Permission } from "./api/rbac";

function RequireAuth({
  children,
  permission,
}: {
  children: ReactNode;
  permission?: Permission;
}) {
  const { isAuthenticated, role } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (permission && !can(role, permission)) {
    return <AppShell><div className="empty">You don’t have access to this area.</div></AppShell>;
  }
  return <AppShell>{children}</AppShell>;
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<RequireAuth><DashboardPage /></RequireAuth>} />
        <Route
          path="/investigations/:id"
          element={<RequireAuth><InvestigationDetailPage /></RequireAuth>}
        />
        <Route path="/incidents" element={<RequireAuth><IncidentsPage /></RequireAuth>} />
        <Route
          path="/audit"
          element={<RequireAuth permission="audit:read"><AuditPage /></RequireAuth>}
        />
        <Route path="/rules" element={<RequireAuth><RulesPage /></RequireAuth>} />
        <Route
          path="/admin"
          element={<RequireAuth permission="admin:*"><AdminPage /></RequireAuth>}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
