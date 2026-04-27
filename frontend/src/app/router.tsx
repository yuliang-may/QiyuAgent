import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAppStore } from "../features/app/store";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { WorkbenchPage } from "../pages/WorkbenchPage";

function ProtectedRoute({ children }: { children: JSX.Element }) {
  const authStatus = useAppStore((state) => state.authStatus);
  const location = useLocation();

  if (authStatus === "unknown") {
    return <div className="screen-loader">正在准备工作台…</div>;
  }

  if (authStatus === "guest") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return children;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/p/:sessionId"
          element={
            <ProtectedRoute>
              <WorkbenchPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
