// Who is logged in. Any component can call useAuth() to get { user, login, logout }.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api";
import { useToast } from "./toast";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));
  const toast = useToast();

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  // A saved token from last visit: ask the server who it belongs to.
  useEffect(() => {
    if (!getToken()) return;
    api("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  // Any 401 later (token expired, user deactivated): log out, and say why.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      logout();
      toast.error("Your session has ended. Please sign in again.");
    });
  }, [logout, toast]);

  const login = useCallback(async (email, password) => {
    const result = await api("/auth/login", { method: "POST", body: { email, password } });
    setToken(result.access_token);
    setUser(result.user);
    return result.user;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export const isStaff = (user) => user?.role === "operator" || user?.role === "admin";
