// The frame around every page after login: sidebar (with counts), a top bar with the page
// title, a bell and the date; on phones a bottom tab bar instead of the sidebar.
import { Bell, ChartColumn, CloudUpload, LayoutGrid, LogOut, Moon, Sun, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, matchPath, useLocation } from "react-router-dom";
import { useApi } from "../api";
import { ChatProvider } from "../chat";
import ChatDock from "./ChatDock";
import { isStaff, useAuth } from "../auth";
import { STATUS, initials } from "../format";
import { useTheme } from "../theme";

// Hiding a link is only for a tidy screen. The server checks every request anyway.
function navItems(user, waiting) {
  const items = [{ to: "/", label: "Requests", icon: LayoutGrid, end: true, count: waiting, tone: "red" }];
  if (isStaff(user)) {
    items.push({ to: "/analytics", label: "Analytics", icon: ChartColumn });
    items.push({ to: "/import", label: "Import", icon: CloudUpload });
  }
  if (user.role === "admin") items.push({ to: "/users", label: "Users", icon: Users });
  return items;
}

function pageTitle(pathname, user) {
  const detail = matchPath("/requests/:id", pathname);
  if (detail) return `Request #${detail.params.id}`;
  return (
    {
      "/": isStaff(user) ? "All requests" : "My requests",
      "/analytics": "Analytics",
      "/import": "Import episodes",
      "/users": "People and roles",
    }[pathname] ?? "Dataset Desk"
  );
}

export function Brand({ compact }) {
  return (
    <div className="brand">
      <div className="brand-mark">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 19V5h6a7 7 0 0 1 0 14H5z" stroke="#fff" strokeWidth="2.6" strokeLinejoin="round" />
          <circle cx="18.5" cy="5.5" r="2.2" fill="#fff" />
        </svg>
      </div>
      {!compact && (
        <div>
          <div className="brand-name">Dataset Desk</div>
          <div className="brand-sub">Robot data requests</div>
        </div>
      )}
    </div>
  );
}

export function ThemeButton({ className = "icon-btn" }) {
  const { theme, toggle } = useTheme();
  const label = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  return (
    <button className={className} onClick={toggle} aria-label={label} title={label}>
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);
  const text = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(now);
  return <span className="date">{text}</span>;
}

/** The bell lists the requests where it is YOUR move (the server says so in allowed_next). */
function BellMenu({ waiting }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div className="bell" ref={box}>
      <button className="icon-btn boxed" onClick={() => setOpen(!open)} aria-label={`${waiting.length} requests need you`} aria-expanded={open}>
        <Bell size={16} />
        {waiting.length > 0 && <span className="bell-count">{waiting.length}</span>}
      </button>
      {open && (
        <div className="dropdown" role="menu">
          <div className="dropdown-head">
            Waiting on you <span className="muted">{waiting.length}</span>
          </div>
          {waiting.length === 0 ? (
            <div className="dropdown-empty">You are all caught up.</div>
          ) : (
            waiting.slice(0, 8).map((r) => (
              <Link key={r.id} to={`/requests/${r.id}`} className="dropdown-item" onClick={() => setOpen(false)}>
                <span className="di-dot" style={{ background: `var(--${STATUS[r.status].tone})` }} />
                <span>
                  <div className="di-title">#{r.id} · {r.task_name}</div>
                  <div className="di-sub">{r.client_name} · {STATUS[r.status].label}</div>
                </span>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const requests = useApi("/requests?limit=200");
  const { reload } = requests;
  useEffect(() => reload(), [location.pathname, reload]); // fresh counts on every page change

  const waiting = (requests.data ?? []).filter((r) => r.allowed_next.length > 0);
  const items = navItems(user, waiting.length);

  return (
    <ChatProvider>
    <div className="app">
      <aside className="sidebar">
        <Brand />
        <div className="nav-label">Workspace</div>
        <nav aria-label="Main">
          {items.map(({ to, label, icon: Icon, end, count, tone }) => (
            <NavLink key={to} to={to} end={end} className="nav-link">
              <Icon size={17} aria-hidden="true" />
              {label}
              {count > 0 && <span className={`nav-count tone-${tone}`} title={`${count} waiting on you`}>{count}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="avatar">{initials(user.name)}</div>
          <div className="who">
            <div className="name">{user.name}</div>
            <div className="role">{user.role}</div>
          </div>
          <ThemeButton />
          <button className="icon-btn" onClick={logout} aria-label="Sign out" title="Sign out">
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      <div style={{ minWidth: 0 }}>
        <header className="topbar">
          <span className="mobile-brand"><Brand compact /></span>
          <h1>{pageTitle(location.pathname, user)}</h1>
          <BellMenu waiting={waiting} />
          <Clock />
          <span className="mobile-brand"><ThemeButton /></span>
          <button className="icon-btn mobile-brand" onClick={logout} aria-label="Sign out" title="Sign out">
            <LogOut size={16} />
          </button>
        </header>

        <main className="main">
          <Outlet />
        </main>

        <nav className="bottom-nav" aria-label="Main">
          {items.map(({ to, label, icon: Icon, end, count, tone }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon size={19} aria-hidden="true" />
              {label}
              {count > 0 && <span className={`nav-count tone-${tone}`}>{count}</span>}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
    <ChatDock />
    </ChatProvider>
  );
}
