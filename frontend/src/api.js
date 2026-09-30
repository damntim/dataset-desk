// One place that talks to the backend. Every page uses api() or useApi().
import { useCallback, useEffect, useState } from "react";

const TOKEN_KEY = "desk.token";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // storage can be blocked (private mode): then we simply are not logged in
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

// auth.jsx sets this, so an expired token anywhere logs the user out.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// Turn FastAPI's error body into one readable sentence.
function messageFrom(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const field = (e.loc || []).filter((p) => p !== "body" && p !== "query").join(".");
        return field ? `${field}: ${e.msg}` : e.msg;
      })
      .join(" · ");
  }
  return `Something went wrong (${status})`;
}

/**
 * api("/requests")                                   -> GET
 * api("/requests", { method: "POST", body: {...} })  -> JSON body
 * api("/episodes/import", { method: "POST", form })  -> file upload
 * Throws ApiError with the server's message when the answer is not 2xx.
 */
export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    payload = form; // the browser sets the multipart Content-Type itself
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`/api${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is it running?");
  }

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    if (response.status === 401 && token) onUnauthorized();
    throw new ApiError(response.status, messageFrom(data, response.status));
  }
  return data;
}

/** Load a path when the component shows (and whenever the path changes).
 *  Returns { data, error, loading, reload }. Pass null to load nothing. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) return undefined;
    let cancelled = false; // ignore answers that arrive after the page moved on
    setState((s) => ({ ...s, loading: true, error: null }));
    api(path).then(
      (data) => !cancelled && setState({ data, error: null, loading: false }),
      (error) => !cancelled && setState({ data: null, error, loading: false }),
    );
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
