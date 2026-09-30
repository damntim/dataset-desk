import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, isStaff, useAuth } from "./auth";
import Layout from "./components/Layout";
import Analytics from "./pages/Analytics";
import Import from "./pages/Import";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import RequestDetail from "./pages/RequestDetail";
import Requests from "./pages/Requests";
import Users from "./pages/Users";
import { ToastProvider } from "./toast";
import "./theme"; // applies the saved light/dark theme before the first paint
import "./styles.css";

function FullPageLoader() {
  return (
    <div className="full-center">
      <div className="brand-mark loader-mark" style={{ width: 52, height: 52 }} aria-label="Loading" />
    </div>
  );
}

/** Only show `children` to logged-in users (and, optionally, only some roles).
 *  This is for a good experience; the API enforces the same rules on its side. */
function Protected({ children, allow }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (allow && !allow(user)) return <Navigate to="/" replace />;
  return children;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Requests />} />
        <Route path="requests/:id" element={<RequestDetail />} />
        <Route path="analytics" element={<Protected allow={isStaff}><Analytics /></Protected>} />
        <Route path="import" element={<Protected allow={isStaff}><Import /></Protected>} />
        <Route path="users" element={<Protected allow={(u) => u.role === "admin"}><Users /></Protected>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
