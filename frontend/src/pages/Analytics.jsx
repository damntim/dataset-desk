import { Activity, Clapperboard, Trophy } from "lucide-react";
import { useMemo, useState } from "react";
import { useApi } from "../api";
import { ErrorNotice, StatTile } from "../components/ui";
import { STATUS, STATUS_ORDER, addDaysIso, formatShortUtcDay, humanDuration, todayIso } from "../format";

// Colour follows the robot, never its rank: each known robot always gets the same slot.
const ROBOTS = ["arm-01", "arm-02", "arm-03", "humanoid-01", "mobile-01"];
const robotColor = (robot) => {
  const slot = ROBOTS.indexOf(robot);
  return slot >= 0 ? `var(--series-${slot + 1})` : "var(--muted)";
};

const PRESETS = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "12 months" },
];

export default function Analytics() {
  const [range, setRange] = useState({ from: addDaysIso(todayIso(), -89), to: todayIso(), preset: 90 });
  const { data, error, loading, reload } = useApi(`/analytics?from=${range.from}&to=${range.to}`);

  const setPreset = (days) => setRange({ from: addDaysIso(todayIso(), -(days - 1)), to: todayIso(), preset: days });

  const totals = useMemo(() => {
    if (!data) return null;
    const perRobot = {};
    let episodes = 0;
    data.episodes_per_day.forEach(({ robot_id, episodes: n }) => {
      perRobot[robot_id] = (perRobot[robot_id] ?? 0) + n;
      episodes += n;
    });
    const busiest = Object.entries(perRobot).sort((a, b) => b[1] - a[1])[0];
    return { episodes, busiest };
  }, [data]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="greet">How the floor is doing</div>
          <p>Recordings per robot, delivery speed, and the tasks with the most good episodes.</p>
        </div>
      </header>

      <section className="range-bar" aria-label="Date range">
        <div className="segmented">
          {PRESETS.map((p) => (
            <button key={p.days} className={`chip ${range.preset === p.days ? "active" : ""}`} onClick={() => setPreset(p.days)}>
              {p.label}
            </button>
          ))}
        </div>
        <label className="sr-only" htmlFor="from">From</label>
        <input id="from" className="input" type="date" value={range.from} max={range.to}
          onChange={(e) => e.target.value && setRange({ ...range, from: e.target.value, preset: null })} />
        <span className="muted">to</span>
        <label className="sr-only" htmlFor="to">To</label>
        <input id="to" className="input" type="date" value={range.to} min={range.from}
          onChange={(e) => e.target.value && setRange({ ...range, to: e.target.value, preset: null })} />
      </section>

      <ErrorNotice error={error} onRetry={reload} />

      <section className="stats" aria-label="Headline numbers">
        <StatTile tone="blue" label="Episodes recorded" value={totals?.episodes.toLocaleString()} sub="in this range" loading={loading && !data} />
        <StatTile tone="violet" label="Busiest robot" value={totals?.busiest ? totals.busiest[0] : "—"}
          sub={totals?.busiest ? `${totals.busiest[1].toLocaleString()} episodes` : undefined} loading={loading && !data} />
        <StatTile tone="amber" label="Requests created" value={data?.requests.total.toLocaleString()}
          sub={data ? `${data.requests.by_status.accepted} accepted` : undefined} loading={loading && !data} />
        <StatTile tone="green" label="Median time to deliver" value={data ? humanDuration(data.requests.median_seconds_to_deliver) : undefined}
          sub={data ? `across ${data.requests.delivered_count} delivered` : undefined} loading={loading && !data} />
      </section>

      <section className="card">
        <div className="card-head">
          <div className="title">
            <Clapperboard size={17} aria-hidden="true" />
            <div>
              <h2>Episodes recorded per day</h2>
              <p className="muted" style={{ fontSize: "0.82rem" }}>Stacked by robot · days in UTC</p>
            </div>
          </div>
          <div className="legend" aria-label="Robots">
            {ROBOTS.map((robot) => (
              <span key={robot}><i className="swatch" style={{ background: robotColor(robot) }} />{robot}</span>
            ))}
          </div>
        </div>
        <div className="card-body">
          {data ? <DailyChart rows={data.episodes_per_day} from={data.from} to={data.to} /> : <div className="skeleton" style={{ height: 280 }} />}
        </div>
        {data && data.episodes_per_day.length > 0 && (
          <details className="table-view">
            <summary>Show as a table</summary>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Day</th><th>Robot</th><th className="num">Episodes</th></tr></thead>
                <tbody>
                  {data.episodes_per_day.map((r) => (
                    <tr key={`${r.day}-${r.robot_id}`}><td>{r.day}</td><td>{r.robot_id}</td><td className="num">{r.episodes}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </section>

      <div className="two-col">
        <section className="card">
          <div className="card-head">
            <div className="title"><Trophy size={17} aria-hidden="true" /><h2>Top tasks by good episodes</h2></div>
          </div>
          <div className="card-body">
            {!data ? <div className="skeleton" style={{ height: 200 }} /> : data.top_tasks_by_good_episodes.length === 0 ? (
              <p className="muted">No good episodes in this range.</p>
            ) : (
              <div className="hbars">
                {data.top_tasks_by_good_episodes.map((t, i) => (
                  <div className="hbar" key={t.task_name}>
                    <div className="hbar-label"><span className={`rank ${i === 0 ? "gold" : ""}`}>{i + 1}</span><span>{t.task_name}</span></div>
                    <div className="hbar-track">
                      <div className="hbar-fill" style={{ width: `${(t.good_episodes / data.top_tasks_by_good_episodes[0].good_episodes) * 100}%` }} />
                    </div>
                    <div className="hbar-value">{t.good_episodes.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <div className="title"><Activity size={17} aria-hidden="true" /><h2>Requests by status</h2></div>
            <span className="muted" style={{ fontSize: "0.82rem" }}>created in this range</span>
          </div>
          <div className="card-body">
            {!data ? <div className="skeleton" style={{ height: 200 }} /> : (
              <div className="hbars">
                {STATUS_ORDER.map((status) => {
                  const count = data.requests.by_status[status];
                  const max = Math.max(1, ...Object.values(data.requests.by_status));
                  const meta = STATUS[status];
                  const Icon = meta.icon;
                  return (
                    <div className="hbar" key={status}>
                      <div className="hbar-label"><Icon size={16} style={{ color: `var(--${meta.tone})` }} aria-hidden="true" /><span>{meta.label}</span></div>
                      <div className="hbar-track">
                        <div className="hbar-fill" style={{ width: `${(count / max) * 100}%`, background: `var(--${meta.tone})` }} />
                      </div>
                      <div className="hbar-value">{count}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// Round the axis maximum up to a friendly number (1, 2, 5, 10, 20, 50, ...).
function niceMax(value) {
  if (value <= 4) return 4;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * power >= value);
  return step * power;
}

function DailyChart({ rows, from, to }) {
  const [hover, setHover] = useState(null);

  // One column for EVERY day in the range, including empty days (an honest time axis).
  const days = useMemo(() => {
    const byDay = {};
    rows.forEach(({ day, robot_id, episodes }) => {
      byDay[day] ??= {};
      byDay[day][robot_id] = episodes;
    });
    const list = [];
    for (let d = new Date(`${from}T00:00:00Z`); d <= new Date(`${to}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) {
      const iso = d.toISOString().slice(0, 10);
      const counts = byDay[iso] ?? {};
      list.push({ day: iso, counts, total: Object.values(counts).reduce((a, b) => a + b, 0) });
    }
    return list;
  }, [rows, from, to]);

  if (rows.length === 0) return <p className="muted">No episodes were recorded in this range.</p>;

  const max = niceMax(Math.max(...days.map((d) => d.total)));
  const labelEvery = Math.ceil(days.length / 7);
  const hovered = hover != null ? days[hover] : null;
  const robotsShown = [...ROBOTS, ...new Set(rows.map((r) => r.robot_id).filter((r) => !ROBOTS.includes(r)))];

  return (
    <div className="chart" onMouseLeave={() => setHover(null)}>
      <div className="chart-plot" role="img" aria-label={`Episodes per day from ${from} to ${to}, stacked by robot`}>
        {[1, 0.5, 0].map((f) => (
          <div key={f} className="chart-grid-line" style={{ bottom: `${f * 100}%` }}>
            <span>{Math.round(max * f)}</span>
          </div>
        ))}
        <div className="chart-area">
        {days.map((d, i) => {
          const segments = robotsShown.filter((robot) => d.counts[robot]);
          return (
            <div
              key={d.day}
              className="chart-col"
              onMouseEnter={() => setHover(i)}
              onClick={() => setHover(i)}
              style={hover === i ? { background: "var(--surface-2)" } : undefined}
            >
              {segments.map((robot, s) => (
                <div
                  key={robot}
                  className={`chart-seg ${s === segments.length - 1 ? "last" : ""}`}
                  style={{ height: `calc(${(d.counts[robot] / max) * 100}% - 2px)`, background: robotColor(robot) }}
                />
              ))}
            </div>
          );
        })}
        {hovered && (
          <div
            className="chart-tooltip"
            style={{
              top: 0,
              // Right half: open to the left of the column; left half: open to the right.
              ...(hover > days.length / 2
                ? { right: `${((days.length - hover) / days.length) * 100}%` }
                : { left: `${((hover + 1) / days.length) * 100}%` }),
            }}
          >
            <div className="tt-title">{formatShortUtcDay(hovered.day)}</div>
            {robotsShown.filter((robot) => hovered.counts[robot]).map((robot) => (
              <div className="tt-row" key={robot}>
                <span className="l"><i className="swatch" style={{ background: robotColor(robot) }} />{robot}</span>
                <strong>{hovered.counts[robot]}</strong>
              </div>
            ))}
            <div className="tt-row tt-total"><span>Total</span><span>{hovered.total}</span></div>
          </div>
        )}
        </div>
      </div>
      <div className="chart-x" aria-hidden="true">
        {days.map((d, i) => (
          <span key={d.day}>{i % labelEvery === 0 ? formatShortUtcDay(d.day) : ""}</span>
        ))}
      </div>
    </div>
  );
}
