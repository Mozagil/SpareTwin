import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { useAuth } from "./auth/AuthProvider";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AssetPage } from "./pages/AssetPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InspectionPage } from "./pages/InspectionPage";
import { InspectionStartPage } from "./pages/InspectionStartPage";
import { LabelsPage } from "./pages/LabelsPage";
import { LoginPage, TenantPicker } from "./pages/LoginPage";
import { PartPage } from "./pages/PartPage";
import { PartsPage } from "./pages/PartsPage";
import { RegisterPage } from "./pages/RegisterPage";
import { RimsPage } from "./pages/RimsPage";
import { StockPage } from "./pages/StockPage";
import { PurchasingPage } from "./pages/PurchasingPage";
import { PurchaseOrderPage } from "./pages/PurchaseOrderPage";
import { MaintenancePage } from "./pages/MaintenancePage";
import { CostsPage } from "./pages/CostsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ModuleGate } from "./components/ModuleGate";

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
          <Route path="jantlar" element={<ModuleGate module="tireiq"><RimsPage /></ModuleGate>} />
          <Route path="stok" element={<ModuleGate module="parts"><StockPage /></ModuleGate>} />
          <Route path="satinalma" element={<ModuleGate module="parts"><PurchasingPage /></ModuleGate>} />
          <Route path="satinalma/:id" element={<ModuleGate module="parts"><PurchaseOrderPage /></ModuleGate>} />
          <Route path="bakim" element={<ModuleGate module="parts"><MaintenancePage /></ModuleGate>} />
          <Route path="maliyet" element={<ModuleGate module="parts"><CostsPage /></ModuleGate>} />
          <Route path="ayarlar" element={<SettingsPage />} />
          <Route path="kontrol" element={<InspectionStartPage />} />
          <Route path="kontrol/:id" element={<InspectionPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
