// The operator's tool: find free episodes (filter by task and quality) and assign them.
import { Bot, ChevronLeft, ChevronRight, Lock, Plus, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, useApi } from "../api";
import { Button, EmptyState, ErrorNotice, QualityBadge } from "../components/ui";
import { formatDateTime, humanDuration, plural } from "../format";
import { useToast } from "../toast";

const PAGE_SIZE = 10;
const ASSIGNABLE = new Set(["good", "usable"]); // same rule as the server (workflow.py)

export default function EpisodePicker({ request, onAssigned }) {
  const toast = useToast();
  const [task, setTask] = useState(request.task_name);
  const [quality, setQuality] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(() => new Map()); // database id -> "EP-00012"
  const [busy, setBusy] = useState(false);

  const params = new URLSearchParams({ unassigned: "true", limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  if (task) params.set("task_name", task);
  if (quality) params.set("quality", quality);
  const list = useApi(`/episodes?${params}`);
  const taskNames = useApi("/episodes/task-names");

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const selectable = items.filter((e) => ASSIGNABLE.has(e.quality));
  const allOnPage = selectable.length > 0 && selectable.every((e) => selected.has(e.id));
  const someOnPage = selectable.some((e) => selected.has(e.id));
  const missing = Math.max(0, request.episodes_requested - request.episodes_assigned);

  // "Select all" shows a dash when only some rows on the page are picked.
  const selectAllRef = useRef(null);
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someOnPage && !allOnPage;
  }, [someOnPage, allOnPage]);

  const changeFilter = (setter) => (e) => {
    setter(e.target.value);
    setPage(0);
  };

  function toggle(episode) {
    const next = new Map(selected);
    if (next.has(episode.id)) next.delete(episode.id);
    else next.set(episode.id, episode.episode_id);
    setSelected(next);
  }

  function togglePage() {
    const next = new Map(selected);
    selectable.forEach((e) => (allOnPage ? next.delete(e.id) : next.set(e.id, e.episode_id)));
    setSelected(next);
  }

  async function assign() {
    setBusy(true);
    try {
      await api(`/requests/${request.id}/assignments`, {
        method: "POST",
        body: { episode_ids: [...selected.keys()] },
      });
      toast.success(`${plural(selected.size, "episode")} assigned`);
      setSelected(new Map());
      list.reload();
      onAssigned();
    } catch (err) {
      toast.error(err.message); // e.g. "Already assigned: EP-00012 (request 4)"
      list.reload();
    } finally {
      setBusy(false);
    }
  }

  const names = new Set(taskNames.data ?? []);
  names.add(request.task_name);

  return (
    <section className="card">
      <div className="card-head">
        <div className="title">
          <SlidersHorizontal size={20} aria-hidden="true" />
          <div>
            <h2>Find episodes</h2>
            <p className="muted" style={{ fontSize: "0.82rem" }}>
              Only free episodes are listed. Bad quality cannot be assigned.
            </p>
          </div>
        </div>
        <span className={`badge ${missing > 0 ? "tone-amber" : "tone-green"}`}>
          {missing > 0 ? `${missing} still needed` : "Enough to deliver"}
        </span>
      </div>

      <div className="picker-filters">
        <label>
          <span className="sr-only">Task</span>
          <select className="select" value={task} onChange={changeFilter(setTask)}>
            <option value="">All tasks</option>
            {[...names].sort().map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Quality</span>
          <select className="select" value={quality} onChange={changeFilter(setQuality)}>
            <option value="">Any quality</option>
            <option value="good">Good</option>
            <option value="usable">Usable</option>
            <option value="bad">Bad</option>
          </select>
        </label>
      </div>

      <ErrorNotice error={list.error} onRetry={list.reload} />

      {list.loading && !list.data ? (
        <div className="card-body"><div className="skeleton" style={{ height: 240 }} /></div>
      ) : items.length === 0 ? (
        <EmptyState icon={Bot} title="No free episodes match">
          Try another task or quality, or import more episodes.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table responsive">
            <thead>
              <tr>
                <th className="check-col">
                  <input
                    ref={selectAllRef}
                    type="checkbox"
                    className="checkbox"
                    checked={allOnPage}
                    onChange={togglePage}
                    disabled={selectable.length === 0}
                    aria-label="Select all on this page"
                  />
                </th>
                <th>Episode</th>
                <th>Robot</th>
                <th>Quality</th>
                <th>Recorded</th>
                <th className="num">Length</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => {
                const allowed = ASSIGNABLE.has(e.quality);
                const isSelected = selected.has(e.id);
                return (
                  <tr
                    key={e.id}
                    className={`${isSelected ? "selected" : ""} ${allowed ? "" : "disabled"}`}
                    onClick={() => allowed && toggle(e)}
                    style={{ cursor: allowed ? "pointer" : "not-allowed" }}
                  >
                    <td className="check-col" data-label="">
                      {allowed ? (
                        <input
                          type="checkbox"
                          className="checkbox"
                          checked={isSelected}
                          onChange={() => toggle(e)}
                          onClick={(event) => event.stopPropagation()}
                          aria-label={`Select ${e.episode_id}`}
                        />
                      ) : (
                        <Lock size={16} className="muted" aria-label="Bad quality: cannot be assigned" />
                      )}
                    </td>
                    <td data-label="Episode" className="cell-title">
                      <div className="cell-strong mono">{e.episode_id}</div>
                      <div className="cell-sub">{e.task_name}</div>
                    </td>
                    <td data-label="Robot"><span className="robot"><Bot size={15} aria-hidden="true" />{e.robot_id}</span></td>
                    <td data-label="Quality"><QualityBadge quality={e.quality} /></td>
                    <td data-label="Recorded" className="nowrap">{formatDateTime(e.recorded_at)}</td>
                    <td data-label="Length" className="num">{humanDuration(e.duration_seconds)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="pager">
        <span>
          {total.toLocaleString()} free episode{total === 1 ? "" : "s"} · page {page + 1} of {pages}
        </span>
        <div className="pager-btns">
          <button className="btn btn-secondary btn-sm" onClick={() => setPage(page - 1)} disabled={page === 0}>
            <ChevronLeft size={16} aria-hidden="true" /> Previous
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setPage(page + 1)} disabled={page + 1 >= pages}>
            Next <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="picker-bar">
          <div>
            <strong>{plural(selected.size, "episode")} selected</strong>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              {selected.size >= missing
                ? "That covers what this request still needs."
                : `${missing - selected.size} more needed after these.`}
            </div>
          </div>
          <div className="actions">
            <button className="btn btn-ghost btn-sm" style={{ color: "inherit" }} onClick={() => setSelected(new Map())}>
              Clear
            </button>
            <Button icon={Plus} busy={busy} onClick={assign}>
              Assign {selected.size}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
