import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { useAuth } from "./auth/AuthProvider";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AssetPage } from "./pages/AssetPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LabelsPage } from "./pages/LabelsPage";
import { LoginPage, TenantPicker } from "./pages/LoginPage";
import { PartPage } from "./pages/PartPage";
import { PartsPage } from "./pages/PartsPage";
import { RegisterPage } from "./pages/RegisterPage";

export function App() {
  const { status, membership } = useAuth();
  if (status === "loading") return <div className="center"><Loading label="Oturum açılıyor" /></div>;
  if (status === "anonymous") return <LoginPage />;
  if (!membership) return <TenantPicker />;
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="makine/:id" element={<AssetPage />} />
          <Route path="parca/:id" element={<PartPage />} />
          <Route path="parcalar" element={<PartsPage />} />
          <Route path="kayit" element={<RegisterPage />} />
          <Route path="etiketler" element={<LabelsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
