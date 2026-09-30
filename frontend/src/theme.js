// Light / dark theme: ONE shared value for the whole app, so every theme button agrees.
// With no saved choice we start dark (the dashboard is designed dark-first).
import { useSyncExternalStore } from "react";

const KEY = "desk.theme";
const listeners = new Set();

function savedTheme() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null; // storage blocked: just use the system setting
  }
}

let current = savedTheme() || "dark";
document.documentElement.dataset.theme = current; // applied before the first paint

function setTheme(next) {
  current = next;
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* ignore */
  }
  listeners.forEach((notify) => notify());
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => current);
  return { theme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}
