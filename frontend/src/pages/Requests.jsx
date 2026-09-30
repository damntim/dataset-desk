import { ArrowRight, CalendarClock, Eye, Inbox, MessageSquare, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApi } from "../api";
import { isStaff, useAuth } from "../auth";
import { useChat } from "../chat";
import { EmptyState, ErrorNotice, StatTile, StatusBadge } from "../components/ui";
import { STATUS, STATUS_ORDER, deadlineInfo, plural } from "../format";
import NewRequestModal from "./NewRequestModal";

const PAGE_LIMIT = 200; // the API maximum; enough for this first version (see NOTES.md)

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

// The four headline tiles. Staff and clients care about different things.
function tiles(user, counts, overdue) {
  if (isStaff(user)) {
    return [
      { key: "submitted", label: "New · to start", tone: "blue", sub: "Waiting for an operator" },
      { key: "in_progress", label: "In progress", tone: "amber", sub: overdue ? `${overdue} overdue` : "On track", subTone: overdue ? "red" : "green" },
      { key: "delivered", label: "Waiting for client", tone: "violet", sub: "Under client review" },
      { key: "rejected", label: "Needs rework", tone: "red", sub: "Sent back by clients" },
    ];
  }
  return [
    { key: "submitted", label: "Submitted", tone: "blue", sub: "Not started yet" },
    { key: "in_progress", label: "Being prepared", tone: "amber", sub: "Operators are working" },
    { key: "delivered", label: "Ready to review", tone: "violet", sub: counts.delivered ? "Your move" : "Nothing to review", subTone: counts.delivered ? "red" : undefined },
    { key: "accepted", label: "Accepted", tone: "green", sub: "All time" },
  ];
}

export default function Requests() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const staff = isStaff(user);
  const { data, error, loading, reload } = useApi(`/requests?limit=${PAGE_LIMIT}`);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);

  const requests = data ?? [];
  const counts = useMemo(() => {
    const result = Object.fromEntries(STATUS_ORDER.map((s) => [s, 0]));
    requests.forEach((r) => (result[r.status] += 1));
    return result;
  }, [requests]);
  const overdue = requests.filter((r) => r.status !== "accepted" && deadlineInfo(r.deadline, r.status).tone === "red").length;
  const yourMove = requests.filter((r) => r.allowed_next.length > 0);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return requests.filter(
      (r) =>
        (filter === "all" || r.status === filter) &&
        (!term || r.task_name.includes(term) || r.client_name.toLowerCase().includes(term) || String(r.id) === term.replace("#", "")),
    );
  }, [requests, filter, search]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="greet">{greeting()}, {user.name.split(" ")[0]}</div>
          <p>{staff ? "Every dataset request across all clients." : `${user.organisation || "Your"} dataset requests, in one place.`}</p>
        </div>
        {user.role === "client" && (
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Plus size={16} aria-hidden="true" /> New request
          </button>
        )}
      </header>

      {yourMove.length > 0 && (
        <div className={`banner ${staff ? "tone-amber" : "tone-violet"}`} role="status">
          <span className="pulse" aria-hidden="true" />
          <span>
            <strong>{plural(yourMove.length, "request")}</strong>{" "}
            {staff ? "waiting for an operator" : "ready for your review"}. Your move.
          </span>
          <span className="spacer" />
          <Link to={`/requests/${yourMove[0].id}`}>
            Open #{yourMove[0].id} <ArrowRight size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} />
          </Link>
        </div>
      )}

      <section className="stats" aria-label="Summary">
        {tiles(user, counts, overdue).map((t) => (
          <StatTile
            key={t.key}
            label={t.label}
            value={counts[t.key]}
            sub={t.sub}
            subTone={t.subTone}
            tone={t.tone}
            loading={loading && !data}
            selected={filter === t.key}
            onClick={() => setFilter(filter === t.key ? "all" : t.key)}
          />
        ))}
      </section>

      <section className="toolbar">
        <div className="segmented" role="group" aria-label="Filter by status">
          <button className={`chip ${filter === "all" ? "active" : ""}`} onClick={() => setFilter("all")}>
            All <span className="count">{requests.length}</span>
          </button>
          {STATUS_ORDER.map((status) => (
            <button key={status} className={`chip ${filter === status ? "active" : ""}`} onClick={() => setFilter(status)}>
              {STATUS[status].label} <span className="count">{counts[status]}</span>
            </button>
          ))}
        </div>
        <label className="input-icon">
          <span className="sr-only">Search requests</span>
          <Search size={15} aria-hidden="true" />
          <input className="input" placeholder={staff ? "Search task, client or #id" : "Search task or #id"} value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
      </section>

      <div className="section-label">{filter === "all" ? "All requests" : STATUS[filter].label} · {visible.length}</div>

      <ErrorNotice error={error} onRetry={reload} />

      {loading && !data ? (
        <div className="req-grid">
          {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton" style={{ height: 176 }} />)}
        </div>
      ) : visible.length === 0 ? (
        <div className="card">
          {requests.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="No requests yet"
              action={user.role === "client" && (
                <button className="btn btn-primary" onClick={() => setCreating(true)}><Plus size={16} aria-hidden="true" /> New request</button>
              )}
            >
              {staff ? "When a client submits a request it shows up here." : "Tell us the task and how many episodes you need."}
            </EmptyState>
          ) : (
            <EmptyState icon={Search} title="Nothing matches">Try another status or search term.</EmptyState>
          )}
        </div>
      ) : (
        <section className="req-grid" aria-label="Requests">
          {visible.map((request) => <RequestCard key={request.id} request={request} staff={staff} />)}
        </section>
      )}

      {requests.length >= PAGE_LIMIT && <p className="muted small">Showing the newest {PAGE_LIMIT} requests.</p>}

      {creating && <NewRequestModal onClose={() => setCreating(false)} onCreated={(created) => navigate(`/requests/${created.id}`)} />}
    </div>
  );
}

function RequestCard({ request: r, staff }) {
  const { openChat } = useChat();
  const deadline = deadlineInfo(r.deadline, r.status);
  const yourTurn = r.allowed_next.length > 0;
  const full = r.episodes_assigned >= r.episodes_requested;

  return (
    <article className={`req-card ${yourTurn && !staff ? "attention" : ""}`}>
      <div className="top">
        <div style={{ minWidth: 0 }}>
          <div className="task">{r.task_name}</div>
          <div className="client">
            <span className="req-id">#{r.id}</span>{staff && ` · ${r.client_name}`}
            {staff && r.operator_name && ` · ${r.operator_name}`}
          </div>
        </div>
        <StatusBadge status={r.status} />
      </div>

      <div className="mini-tiles">
        <div className="mini-tile tone-blue"><strong>{r.episodes_requested}</strong><span>Requested</span></div>
        <div className={`mini-tile ${full ? "tone-green" : "tone-amber"}`}><strong>{r.episodes_assigned}</strong><span>Assigned</span></div>
        <div className={`mini-tile ${r.episodes_rejected ? "tone-red" : "tone-neutral"}`}><strong>{r.episodes_rejected}</strong><span>Rejected</span></div>
      </div>

      <div className="chips">
        <span className={`badge tone-${deadline.tone}`}><CalendarClock aria-hidden="true" /> {deadline.text}</span>
        {yourTurn && <span className="badge tone-violet">Your move</span>}
        {r.can_read_chat && (
          <span className={`right ${r.unread_messages ? "has-unread" : ""}`} title={r.unread_messages ? `${r.unread_messages} unread` : "Messages"}>
            <MessageSquare size={13} aria-hidden="true" /> {r.unread_messages ? `${r.unread_messages} new` : r.message_count}
          </span>
        )}
      </div>

      <div className="foot" style={r.can_read_chat ? undefined : { gridTemplateColumns: "1fr" }}>
        {r.can_read_chat && (
          <button className="btn btn-secondary btn-sm" onClick={() => openChat(r.id)}>
            <MessageSquare size={14} aria-hidden="true" /> {r.can_write_chat ? "Chat" : "Read chat"}
            {r.unread_messages > 0 && <span className="unread-badge">{r.unread_messages}</span>}
          </button>
        )}
        <Link to={`/requests/${r.id}`} className="btn btn-secondary btn-sm"><Eye size={14} aria-hidden="true" /> View</Link>
      </div>
    </article>
  );
}
