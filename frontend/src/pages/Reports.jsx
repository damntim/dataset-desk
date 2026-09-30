// Admin insight report: speed, quality, people, and what needs attention now.
// Every number comes from GET /reports/overview (computed in PostgreSQL).
import { AlarmClock, Bot, Crown, Medal, ThumbsDown, TrendingUp, Trophy, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../api";
import { ErrorNotice, StatTile, StatusBadge } from "../components/ui";
import { addDaysIso, formatDateTime, formatDay, formatShortUtcDay, humanDuration, todayIso } from "../format";

const PRESETS = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "12 months" },
];
const pct = (rate) => (rate == null ? "—" : `${Math.round(rate * 100)}%`);

export default function Reports() {
  const [range, setRange] = useState({ from: addDaysIso(todayIso(), -89), to: todayIso(), preset: 90 });
  const { data, error, loading, reload } = useApi(`/reports/overview?from=${range.from}&to=${range.to}`);
  const setPreset = (days) => setRange({ from: addDaysIso(todayIso(), -(days - 1)), to: todayIso(), preset: days });
  const k = data?.kpis;
  const waiting = loading && !data;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="greet">Insights report</div>
          <p>How fast we respond and deliver, what clients reject, and who does it best.</p>
        </div>
        <div className="range-bar">
          <div className="segmented">
            {PRESETS.map((p) => (
              <button key={p.days} className={`chip ${range.preset === p.days ? "active" : ""}`} onClick={() => setPreset(p.days)}>
                {p.label}
              </button>
            ))}
          </div>
          <input className="input" type="date" aria-label="From" value={range.from} max={range.to}
            onChange={(e) => e.target.value && setRange({ ...range, from: e.target.value, preset: null })} />
          <input className="input" type="date" aria-label="To" value={range.to} min={range.from}
            onChange={(e) => e.target.value && setRange({ ...range, to: e.target.value, preset: null })} />
        </div>
      </header>

      <ErrorNotice error={error} onRetry={reload} />

      <section className="stats" aria-label="Headline numbers">
        <StatTile tone="blue" label="Requests" value={k?.requests} sub={k && `${k.delivered} delivered`} loading={waiting} />
        <StatTile tone="green" label="Accepted" value={k?.accepted}
          sub={k && `${pct(k.delivered ? k.accepted / k.delivered : null)} of delivered`} loading={waiting} />
        <StatTile tone={k?.on_time_rate != null && k.on_time_rate < 0.8 ? "red" : "green"} label="On-time delivery"
          value={k && pct(k.on_time_rate)} sub="delivered by the deadline" loading={waiting} />
        <StatTile tone={k?.episode_rejection_rate > 0.15 ? "red" : "amber"} label="Episodes rejected"
          value={k && pct(k.episode_rejection_rate)} sub={k && `${k.episodes_rejected} of ${k.episodes_reviewed} reviewed`} loading={waiting} />
        <StatTile tone="violet" label="First response" value={k && humanDuration(k.median_first_response_seconds)}
          sub="median: submitted → work starts" loading={waiting} />
        <StatTile tone="violet" label="Delivery time" value={k && humanDuration(k.median_delivery_seconds)}
          sub="median: submitted → delivered" loading={waiting} />
        <StatTile tone="blue" label="Client review" value={k && humanDuration(k.median_client_review_seconds)}
          sub="median: delivered → decision" loading={waiting} />
        <StatTile tone="neutral" label="Episodes delivered" value={k?.episodes_delivered} sub="in these requests" loading={waiting} />
      </section>

      {data?.top_operator && <Spotlight op={data.top_operator} />}

      <section className="card">
        <div className="card-head">
          <div className="title"><TrendingUp size={17} aria-hidden="true" /><h2>Weekly flow</h2></div>
          <div className="legend">
            {SERIES.map((s) => <span key={s.key}><i className="swatch" style={{ background: s.color }} />{s.label}</span>)}
          </div>
        </div>
        <div className="card-body">{data ? <WeeklyChart weeks={data.weekly} /> : <div className="skeleton" style={{ height: 200 }} />}</div>
      </section>

      <section className="card">
        <div className="card-head"><div className="title"><Trophy size={17} aria-hidden="true" /><h2>Operator leaderboard</h2></div>
          <span className="muted small">ranked by accepted requests, then episode acceptance, then speed</span></div>
        <Leaderboard operators={data?.operators} />
      </section>

      <div className="two-col">
        <section className="card">
          <div className="card-head"><div className="title"><Users size={17} aria-hidden="true" /><h2>Clients</h2></div>
            <span className="muted small">highest rejection rate first</span></div>
          <ClientTable clients={data?.clients} />
        </section>
        <section className="card">
          <div className="card-head"><div className="title"><AlarmClock size={17} aria-hidden="true" /><h2>At risk now</h2></div>
            <span className="muted small">open, overdue or due within 3 days</span></div>
          <AtRisk rows={data?.at_risk} />
        </section>
      </div>

      <div className="two-col">
        <RejectionBars title="Rejected by robot" icon={Bot} rows={data?.rejections_by_robot} ids />
        <RejectionBars title="Rejected by task" icon={ThumbsDown} rows={data?.rejections_by_task} />
      </div>

      <section className="card">
        <div className="card-head"><div className="title"><ThumbsDown size={17} aria-hidden="true" /><h2>Videos rejected by clients</h2></div>
          {data && <span className="badge tone-red">{data.rejected_episodes.length}</span>}</div>
        <RejectedList rows={data?.rejected_episodes} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- pieces

function Spotlight({ op }) {
  return (
    <section className="spotlight">
      <div className="spot-crown"><Crown size={22} aria-hidden="true" /></div>
      <div className="spot-who">
        <div className="section-label">Top operator</div>
        <div className="spot-name">{op.name}</div>
      </div>
      <div className="spot-stats">
        <div><strong>{op.accepted}</strong><span>accepted requests</span></div>
        <div><strong>{pct(op.episode_acceptance_rate)}</strong><span>episodes kept by clients</span></div>
        <div><strong>{pct(op.on_time_rate)}</strong><span>on time</span></div>
        <div><strong>{humanDuration(op.median_delivery_seconds)}</strong><span>median delivery</span></div>
      </div>
    </section>
  );
}

const SERIES = [
  { key: "created", label: "Created", color: "var(--series-1)" },
  { key: "delivered", label: "Delivered", color: "var(--series-3)" },
  { key: "accepted", label: "Accepted", color: "var(--series-2)" },
];

function WeeklyChart({ weeks }) {
  const [hover, setHover] = useState(null);
  if (weeks.length === 0) return <p className="muted">Nothing happened in this range.</p>;
  const max = Math.max(4, ...weeks.flatMap((w) => SERIES.map((s) => w[s.key])));
  const top = Math.ceil(max / 2) * 2;
  const shown = hover != null ? weeks[hover] : null;
  return (
    <div className="chart" onMouseLeave={() => setHover(null)}>
      <div className="chart-plot">
        {[1, 0.5, 0].map((f) => (
          <div key={f} className="chart-grid-line" style={{ bottom: `${f * 100}%` }}><span>{Math.round(top * f)}</span></div>
        ))}
        <div className="chart-area" style={{ gap: 10 }}>
          {weeks.map((w, i) => (
            <div key={w.week} className="chart-group" onMouseEnter={() => setHover(i)} onClick={() => setHover(i)}
              style={hover === i ? { background: "var(--surface-2)" } : undefined}>
              {SERIES.map((s) => (
                <div key={s.key} className="chart-bar" style={{ height: `${(w[s.key] / top) * 100}%`, background: s.color }} />
              ))}
            </div>
          ))}
          {shown && (
            <div className="chart-tooltip" style={{ top: 0, ...(hover > weeks.length / 2
              ? { right: `${((weeks.length - hover) / weeks.length) * 100}%` }
              : { left: `${((hover + 1) / weeks.length) * 100}%` }) }}>
              <div className="tt-title">Week of {formatShortUtcDay(shown.week)}</div>
              {SERIES.map((s) => (
                <div className="tt-row" key={s.key}><span className="l"><i className="swatch" style={{ background: s.color }} />{s.label}</span><strong>{shown[s.key]}</strong></div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="chart-x" style={{ gap: 10 }} aria-hidden="true">
        {weeks.map((w) => <span key={w.week} style={{ textAlign: "center" }}>{formatShortUtcDay(w.week)}</span>)}
      </div>
    </div>
  );
}

function RateBar({ rate, tone = "green" }) {
  if (rate == null) return <span className="muted">—</span>;
  return (
    <span className="rate">
      <span className="rate-track"><span className={`rate-fill tone-fill-${tone}`} style={{ width: `${Math.round(rate * 100)}%` }} /></span>
      <span className="rate-v">{pct(rate)}</span>
    </span>
  );
}

function Leaderboard({ operators }) {
  if (!operators) return <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>;
  if (operators.length === 0) return <p className="muted card-body">No operator worked on requests in this range.</p>;
  return (
    <div className="table-wrap">
      <table className="table responsive">
        <thead><tr><th>#</th><th>Operator</th><th className="num">Requests</th><th className="num">Delivered</th><th className="num">Accepted</th>
          <th>On time</th><th>Episodes kept</th><th className="num">Median delivery</th></tr></thead>
        <tbody>
          {operators.map((o, i) => (
            <tr key={o.user_id}>
              <td data-label="Rank">{i < 3 ? <Medal size={18} className={`medal medal-${i}`} aria-label={`Rank ${i + 1}`} /> : i + 1}</td>
              <td data-label="Operator" className="cell-title"><span className="cell-strong">{o.name}</span>
                <div className="cell-sub">{o.episodes_assigned} episodes assigned · {o.episodes_rejected} rejected</div></td>
              <td data-label="Requests" className="num">{o.requests}</td>
              <td data-label="Delivered" className="num">{o.delivered}</td>
              <td data-label="Accepted" className="num cell-strong">{o.accepted}</td>
              <td data-label="On time"><RateBar rate={o.on_time_rate} tone={o.on_time_rate < 0.8 ? "amber" : "green"} /></td>
              <td data-label="Episodes kept"><RateBar rate={o.episode_acceptance_rate} tone={o.episode_acceptance_rate < 0.85 ? "amber" : "green"} /></td>
              <td data-label="Median delivery" className="num">{humanDuration(o.median_delivery_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClientTable({ clients }) {
  if (!clients) return <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>;
  if (clients.length === 0) return <p className="muted card-body">No requests in this range.</p>;
  return (
    <div className="table-wrap">
      <table className="table responsive">
        <thead><tr><th>Client</th><th className="num">Requests</th><th className="num">Accepted</th><th>Rejection rate</th><th className="num">Review time</th></tr></thead>
        <tbody>
          {clients.map((c) => (
            <tr key={c.user_id}>
              <td data-label="Client" className="cell-title"><span className="cell-strong">{c.name}</span>
                <div className="cell-sub">{c.episodes_rejected} of {c.episodes_reviewed} episodes rejected</div></td>
              <td data-label="Requests" className="num">{c.requests}</td>
              <td data-label="Accepted" className="num">{c.accepted}</td>
              <td data-label="Rejection rate"><RateBar rate={c.rejection_rate} tone="red" /></td>
              <td data-label="Review time" className="num">{humanDuration(c.median_review_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AtRisk({ rows }) {
  if (!rows) return <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>;
  if (rows.length === 0) return <p className="muted card-body">Nothing at risk. 🎉</p>;
  return (
    <ul className="risk-list">
      {rows.map((r) => (
        <li key={r.id}>
          <Link to={`/requests/${r.id}`} className="risk-item">
            <span className={`risk-days ${r.days_left < 0 ? "tone-red" : "tone-amber"}`}>
              <strong>{r.days_left < 0 ? -r.days_left : r.days_left}</strong>
              <span>{r.days_left < 0 ? "days late" : r.days_left === 0 ? "today" : "days left"}</span>
            </span>
            <span className="risk-body">
              <span className="risk-top"><strong>#{r.id} · {r.task_name}</strong><StatusBadge status={r.status} /></span>
              <span className="cell-sub">{r.client_name} · {r.operator_name ?? "no operator yet"} · due {formatDay(r.deadline)} · {r.episodes_assigned}/{r.episodes_requested} episodes</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RejectionBars({ title, icon: Icon, rows, ids }) {
  return (
    <section className="card">
      <div className="card-head"><div className="title"><Icon size={17} aria-hidden="true" /><h2>{title}</h2></div>
        <span className="muted small">share of reviewed episodes</span></div>
      <div className="card-body">
        {!rows ? <div className="skeleton" style={{ height: 120 }} /> : rows.length === 0 ? <p className="muted">No reviewed episodes yet.</p> : (
          <div className="hbars">
            {rows.slice(0, 7).map((r) => (
              <div className="hbar" key={r.key}>
                <div className="hbar-label" style={ids ? { textTransform: "none" } : undefined}><span className={ids ? "mono" : undefined}>{r.key}</span></div>
                <div className="hbar-track"><div className="hbar-fill" style={{ width: `${Math.max(2, (r.rate ?? 0) * 100)}%`, background: "var(--red)" }} /></div>
                <div className="hbar-value" title={`${r.rejected} of ${r.reviewed}`}>{pct(r.rate)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function RejectedList({ rows }) {
  if (!rows) return <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>;
  if (rows.length === 0) return <p className="muted card-body">No video was rejected in this range.</p>;
  return (
    <div className="table-wrap">
      <table className="table responsive">
        <thead><tr><th>Episode</th><th>Request</th><th>Client</th><th>Assigned by</th><th>Reason</th><th>When</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.request_id}-${r.id}`}>
              <td data-label="Episode" className="cell-title"><span className="cell-strong mono">{r.episode_id}</span>
                <div className="cell-sub">{r.robot_id} · {r.task_name}</div></td>
              <td data-label="Request"><Link to={`/requests/${r.request_id}`} className="link">#{r.request_id}</Link></td>
              <td data-label="Client">{r.client_name}</td>
              <td data-label="Assigned by">{r.assigned_by_name}</td>
              <td data-label="Reason" className="full"><span className="verdict-note" style={{ fontSize: "0.8rem" }}>{r.review_note ? `“${r.review_note}”` : "—"}</span></td>
              <td data-label="When" className="nowrap">{formatDateTime(r.reviewed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
