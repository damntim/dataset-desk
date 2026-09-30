// The client's review of a delivery: for each new episode choose Keep, Return or Reject.
//   Keep   = I want it.
//   Return = fine, but more than I asked for: give it back (free for other requests).
//   Reject = not good enough: the request goes back for rework (reason required).
// If the client keeps MORE than requested, they must return the extras or extend the request.
// The server checks every one of these rules again (POST /requests/{id}/review).
import { Bot, Check, CircleX, ClipboardCheck, Expand, RotateCcw, Undo2 } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { Button, QualityBadge } from "../components/ui";
import { formatDateTime, humanDuration, plural } from "../format";
import { useToast } from "../toast";
import { VerdictBadge } from "./RequestEpisodes";

const CHOICES = [
  { key: "keep", label: "Keep", icon: Check },
  { key: "return", label: "Return", icon: Undo2 },
  { key: "reject", label: "Reject", icon: CircleX },
];

export default function ReviewPanel({ request, episodes, onDone }) {
  const toast = useToast();
  const [choice, setChoice] = useState({}); // episode id -> "keep" | "return" | "reject"
  const [reason, setReason] = useState("");
  const [extend, setExtend] = useState(false);
  const [busy, setBusy] = useState(false);

  const pending = episodes.filter((e) => e.review_status === "pending");
  const acceptedEarlier = episodes.filter((e) => e.review_status === "accepted").length;
  const get = (id) => choice[id] ?? "keep";
  const rejects = pending.filter((e) => get(e.id) === "reject");
  const returns = pending.filter((e) => get(e.id) === "return");
  const kept = acceptedEarlier + pending.length - rejects.length - returns.length;
  const wanted = request.episodes_requested;

  const mode = rejects.length > 0 ? "rework" : kept < wanted ? "short" : kept > wanted ? "over" : "exact";
  const canSubmit = { rework: reason.trim().length > 0, short: false, over: extend, exact: true }[mode];

  const setAll = (value) => setChoice(Object.fromEntries(pending.map((e) => [e.id, value])));

  // "Keep only N": mark the last extra kept episodes as Return.
  function keepOnlyWanted() {
    const next = { ...choice };
    let extra = kept - wanted;
    for (const e of [...pending].reverse()) {
      if (extra <= 0) break;
      if (get(e.id) === "keep") {
        next[e.id] = "return";
        extra -= 1;
      }
    }
    setChoice(next);
    setExtend(false);
  }

  async function submit() {
    setBusy(true);
    try {
      await api(`/requests/${request.id}/review`, {
        method: "POST",
        body: {
          rejected_episode_ids: rejects.map((e) => e.id),
          returned_episode_ids: returns.map((e) => e.id),
          reason: reason.trim() || null,
          extend: mode === "over" && extend,
        },
      });
      toast.success(mode === "rework" ? "Sent back for rework" : `Delivery accepted: ${plural(kept, "episode")} kept`);
      onDone();
    } catch (err) {
      toast.error(err.message);
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div className="title">
          <ClipboardCheck size={17} aria-hidden="true" />
          <h2>Review this delivery</h2>
        </div>
        <div className="actions">
          <button className="btn btn-ghost btn-sm" onClick={() => setAll("keep")}><Check size={14} aria-hidden="true" /> Keep all</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setAll("reject")}><CircleX size={14} aria-hidden="true" /> Reject all</button>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table responsive">
          <thead>
            <tr><th>Episode</th><th>Robot</th><th>Quality</th><th>Recorded</th><th className="num">Length</th><th>Your decision</th></tr>
          </thead>
          <tbody>
            {episodes.map((e) => {
              const current = get(e.id);
              return (
                <tr key={e.id} className={e.review_status === "pending" && current === "reject" ? "rejected-row" : ""}>
                  <td data-label="Episode" className="cell-title">
                    <div className="cell-strong mono">{e.episode_id}</div>
                    <div className="cell-sub">{e.task_name}</div>
                  </td>
                  <td data-label="Robot"><span className="robot"><Bot size={13} aria-hidden="true" />{e.robot_id}</span></td>
                  <td data-label="Quality"><QualityBadge quality={e.quality} /></td>
                  <td data-label="Recorded" className="nowrap">{formatDateTime(e.recorded_at)}</td>
                  <td data-label="Length" className="num">{humanDuration(e.duration_seconds)}</td>
                  <td data-label="Decision" className="full">
                    {e.review_status === "pending" ? (
                      <div className="seg3" role="radiogroup" aria-label={`Decision for ${e.episode_id}`}>
                        {CHOICES.map(({ key, label, icon: Icon }) => (
                          <button
                            key={key}
                            type="button"
                            role="radio"
                            aria-checked={current === key}
                            className={`${key} ${current === key ? "on" : ""}`}
                            onClick={() => setChoice({ ...choice, [e.id]: key })}
                          >
                            <Icon size={12} aria-hidden="true" /> {label}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <VerdictBadge episode={e} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="review-bar">
        <div className="tally">
          <span className="badge tone-green">Keeping {kept}</span>
          {returns.length > 0 && <span className="badge tone-blue">Returning {returns.length}</span>}
          {rejects.length > 0 && <span className="badge tone-red">Rejecting {rejects.length}</span>}
          <span className="muted">You requested {wanted}.</span>
        </div>

        {mode === "over" && (
          <div className="choice-box">
            <strong className="small">
              You are keeping {kept} episodes but asked for {wanted}. Choose one:
            </strong>
            <div className="opts">
              <button className="btn btn-secondary btn-sm" onClick={keepOnlyWanted}>
                <RotateCcw size={14} aria-hidden="true" /> Keep only {wanted}, return {kept - wanted}
              </button>
              <button className={`btn btn-sm ${extend ? "btn-primary" : "btn-secondary"}`} onClick={() => setExtend(!extend)} aria-pressed={extend}>
                <Expand size={14} aria-hidden="true" /> Extend my request to {kept}
              </button>
            </div>
          </div>
        )}

        {mode === "short" && (
          <div className="notice tone-amber">
            You asked for {wanted}; keep at least {wanted}, or reject some to get replacements.
          </div>
        )}

        {mode === "rework" && (
          <label className="field">
            <span>Why are you rejecting {plural(rejects.length, "episode")}?</span>
            <textarea className="textarea" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000}
              placeholder="e.g. The gripper is out of frame in these clips" />
          </label>
        )}

        <div className="actions">
          <Button
            kind={mode === "rework" ? "danger" : "success"}
            icon={mode === "rework" ? CircleX : Check}
            busy={busy}
            disabled={!canSubmit}
            onClick={submit}
          >
            {mode === "rework"
              ? `Reject ${rejects.length} and send back for rework`
              : mode === "over" && extend
                ? `Accept ${kept} and extend my request`
                : `Accept ${plural(kept, "episode")}`}
          </Button>
        </div>
      </div>
    </section>
  );
}
