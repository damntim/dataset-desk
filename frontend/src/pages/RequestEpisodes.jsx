// The list of episodes in a request (outside the client's review), with each verdict.
import { Bot, Clapperboard, Lock, Trash2 } from "lucide-react";
import { EmptyState, ErrorNotice, QualityBadge } from "../components/ui";
import { formatDateTime, humanDuration, plural } from "../format";

const VERDICT = {
  pending: { label: "Not reviewed", tone: "neutral" },
  accepted: { label: "Accepted", tone: "green" },
  rejected: { label: "Rejected", tone: "red" },
};

export function VerdictBadge({ episode }) {
  const v = VERDICT[episode.review_status];
  return (
    <div>
      <span className={`badge tone-${v.tone}`}>{v.label}</span>
      {episode.review_status === "rejected" && episode.review_note && (
        <div className="verdict-note">“{episode.review_note}”</div>
      )}
    </div>
  );
}

export default function RequestEpisodes({ state, request, canEdit, removing, onRemove }) {
  const title = ["delivered", "accepted"].includes(request.status) ? "Delivered episodes" : "Assigned episodes";
  const total = state.data?.length ?? 0;

  return (
    <section className="card">
      <div className="card-head">
        <div className="title"><Clapperboard size={17} aria-hidden="true" /><h2>{title}</h2></div>
        <span className="badge tone-neutral">{plural(total, "episode")}</span>
      </div>
      {state.error ? (
        <div className="card-body"><ErrorNotice error={state.error} onRetry={state.reload} /></div>
      ) : !state.data ? (
        <div className="card-body"><div className="skeleton" style={{ height: 100 }} /></div>
      ) : total === 0 ? (
        <EmptyState icon={Clapperboard} title="No episodes yet">
          {canEdit ? "Pick episodes from the list below." : "Episodes appear here as operators assign them."}
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table responsive">
            <thead>
              <tr>
                <th>Episode</th><th>Robot</th><th>Quality</th><th>Recorded</th><th className="num">Length</th><th>Client review</th>
                {canEdit && <th><span className="sr-only">Remove</span></th>}
              </tr>
            </thead>
            <tbody>
              {state.data.map((e) => (
                <tr key={e.id} className={e.review_status === "rejected" ? "rejected-row" : ""}>
                  <td data-label="Episode" className="cell-title">
                    <div className="cell-strong mono">{e.episode_id}</div>
                    <div className="cell-sub">{e.task_name}</div>
                  </td>
                  <td data-label="Robot"><span className="robot"><Bot size={13} aria-hidden="true" />{e.robot_id}</span></td>
                  <td data-label="Quality"><QualityBadge quality={e.quality} /></td>
                  <td data-label="Recorded" className="nowrap">{formatDateTime(e.recorded_at)}</td>
                  <td data-label="Length" className="num">{humanDuration(e.duration_seconds)}</td>
                  <td data-label="Review" className="full"><VerdictBadge episode={e} /></td>
                  {canEdit && (
                    <td data-label="" className="row-action">
                      {e.review_status === "accepted" ? (
                        <span className="icon-btn" title="Accepted by the client: it stays" aria-label="Locked"><Lock size={14} /></span>
                      ) : (
                        <button className="icon-btn danger" onClick={() => onRemove(e)} disabled={removing === e.id}
                          aria-label={`Remove ${e.episode_id}`} title="Remove from this request">
                          <Trash2 size={14} />
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
