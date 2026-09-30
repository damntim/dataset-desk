import { ArrowLeft, BadgeCheck, CircleX, History, Info, MessageCircle, PackageCheck, Send, Wrench } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, useApi } from "../api";
import { isStaff, useAuth } from "../auth";
import { useChat } from "../chat";
import { Button, EmptyState, ErrorNotice, Modal, ProgressRing, StatusBadge } from "../components/ui";
import { STATUS, actionFor, deadlineInfo, formatDateTime, formatDay, plural } from "../format";
import { useToast } from "../toast";
import EpisodePicker from "./EpisodePicker";
import RequestEpisodes from "./RequestEpisodes";
import ReviewPanel from "./ReviewPanel";

export default function RequestDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const { openChat } = useChat();
  const toast = useToast();
  const request = useApi(`/requests/${id}`);
  const episodes = useApi(`/requests/${id}/episodes`);
  const [confirming, setConfirming] = useState(null);
  const [moving, setMoving] = useState(null);
  const [removing, setRemoving] = useState(null);

  const refresh = () => {
    request.reload();
    episodes.reload();
  };

  if (request.error?.status === 404) {
    return (
      <div className="page">
        <div className="card">
          <EmptyState icon={Info} title="Request not found" action={<Link className="btn btn-primary" to="/">Back to requests</Link>}>
            It does not exist, or it is not yours to see.
          </EmptyState>
        </div>
      </div>
    );
  }
  if (!request.data) {
    return (
      <div className="page">
        <ErrorNotice error={request.error} onRetry={request.reload} />
        {!request.error && [70, 90, 300].map((h) => <div key={h} className="skeleton" style={{ height: h }} />)}
      </div>
    );
  }

  const r = request.data;
  const staff = isStaff(user);
  const canEditEpisodes = staff && r.status === "in_progress";
  const clientReviewing = user.role === "client" && r.status === "delivered";

  async function moveTo(status) {
    setMoving(status);
    try {
      await api(`/requests/${r.id}/status`, { method: "PATCH", body: { status } });
      toast.success(`Request #${r.id} is now ${STATUS[status].label.toLowerCase()}`);
      setConfirming(null);
      refresh();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setMoving(null);
    }
  }

  async function unassign(episode) {
    setRemoving(episode.id);
    try {
      await api(`/requests/${r.id}/assignments/${episode.id}`, { method: "DELETE" });
      toast.success(`${episode.episode_id} removed`);
      refresh();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRemoving(null);
    }
  }

  const deadline = deadlineInfo(r.deadline, r.status);
  const reworks = r.history.filter((h) => h.to_status === "rejected").length;

  return (
    <div className="page">
      <Link to="/" className="back-link"><ArrowLeft size={14} aria-hidden="true" /> All requests</Link>

      <div className="card"><Stepper request={r} /></div>

      <div className="detail-grid">
        <div className="stack">
          <section className="card card-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="info-title">
              <h2>{r.task_name}</h2>
              <StatusBadge status={r.status} />
              {reworks > 0 && <span className="badge tone-neutral">Reworked {reworks}×</span>}
              {r.can_read_chat && (
                <button className="btn btn-secondary btn-sm" style={{ marginLeft: "auto" }} onClick={() => openChat(r.id)}>
                  <MessageCircle size={14} aria-hidden="true" /> {r.can_write_chat ? "Chat" : "Read chat"}
                  {r.unread_messages > 0 && <span className="unread-badge">{r.unread_messages}</span>}
                </button>
              )}
            </div>
            {r.notes && <div className="quote">{r.notes}</div>}
            <dl className="meta-grid" style={{ margin: 0 }}>
              <div><dt>Client</dt><dd className="v" style={{ margin: 0 }}>{r.client_name}</dd></div>
              <div><dt>Operator</dt><dd className="v" style={{ margin: 0 }}>{r.operator_name ?? "Not assigned yet"}</dd></div>
              <div><dt>Submitted</dt><dd className="v" style={{ margin: 0 }}>{formatDateTime(r.created_at)}</dd></div>
              <div>
                <dt>Deadline</dt>
                <dd className="v" style={{ margin: 0 }}>{formatDay(r.deadline)} <span className={`badge tone-${deadline.tone}`}>{deadline.text}</span></dd>
              </div>
              <div><dt>Requested</dt><dd className="v" style={{ margin: 0 }}>{r.episodes_requested}</dd></div>
              <div><dt>Assigned</dt><dd className="v" style={{ margin: 0 }}>{r.episodes_assigned}</dd></div>
              <div><dt>Rejected by client</dt><dd className="v" style={{ margin: 0, color: r.episodes_rejected ? "var(--red)" : undefined }}>{r.episodes_rejected}</dd></div>
            </dl>
          </section>

          {clientReviewing && episodes.data ? (
            <ReviewPanel request={r} episodes={episodes.data} onDone={refresh} />
          ) : (
            <RequestEpisodes state={episodes} request={r} canEdit={canEditEpisodes} removing={removing} onRemove={unassign} />
          )}

          {canEditEpisodes && <EpisodePicker request={r} onAssigned={refresh} />}

        </div>

        <div className="stack">
          <section className="card">
            <ActionBox request={r} staff={staff} moving={moving} clientReviewing={clientReviewing}
              onMove={(status) => (status === "accepted" || status === "rejected" ? setConfirming(status) : moveTo(status))} />
          </section>

          <section className="card progress-box">
            <ProgressRing value={r.episodes_assigned} max={r.episodes_requested} />
            <dl className="kv">
              <dt>Requested</dt><dd>{r.episodes_requested}</dd>
              <dt>Counting</dt><dd>{r.episodes_assigned}</dd>
              <dt>Extra</dt><dd>{Math.max(0, r.episodes_assigned - r.episodes_requested)}</dd>
              <dt>Missing</dt><dd>{Math.max(0, r.episodes_requested - r.episodes_assigned)}</dd>
            </dl>
          </section>

          <section className="card">
            <div className="card-head"><div className="title"><History size={17} aria-hidden="true" /><h2>History</h2></div></div>
            <div className="card-body"><Timeline history={r.history} /></div>
          </section>
        </div>
      </div>

      {confirming && (
        <ConfirmDecision status={confirming} request={r} busy={moving === confirming}
          onCancel={() => setConfirming(null)} onConfirm={() => moveTo(confirming)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the status stepper

const STEPS = [
  { key: "submitted", label: "Submitted", icon: Send },
  { key: "in_progress", label: "In progress", icon: Wrench },
  { key: "delivered", label: "Delivered", icon: PackageCheck },
];

function Stepper({ request }) {
  const final = request.status === "rejected"
    ? { key: "rejected", label: "Rejected", icon: CircleX }
    : { key: "accepted", label: "Accepted", icon: BadgeCheck };
  const steps = [...STEPS, final];
  const position = { submitted: 0, in_progress: 1, delivered: 2, accepted: 3, rejected: 3 }[request.status];
  const reachedAt = {};
  request.history.forEach((h) => (reachedAt[h.to_status] = h.changed_at)); // last time each was reached

  return (
    <ol className="stepper" aria-label="Request progress">
      {steps.map((step, index) => {
        const state = index < position ? "done" : index === position ? "current" : "todo";
        const tone = step.key === "accepted" ? "good" : step.key === "rejected" ? "bad" : "";
        const Icon = step.icon;
        return (
          <li key={step.key} className={`step ${state} ${tone}`} aria-current={state === "current" ? "step" : undefined}>
            <div className="step-dot"><Icon aria-hidden="true" /></div>
            <div className="step-name">{step.label}</div>
            {state !== "todo" && reachedAt[step.key] && <div className="step-when">{formatDateTime(reachedAt[step.key])}</div>}
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------- what can I do now?

function explain(r, staff) {
  const missing = r.episodes_requested - r.episodes_assigned;
  const texts = staff
    ? {
        submitted: ["New request", "Start work to begin assigning episodes."],
        in_progress: missing > 0
          ? ["Assembling the dataset", `Assign ${plural(missing, "more episode")}, then deliver.`]
          : ["Ready to deliver", "Enough episodes are assigned. Deliver it to the client."],
        delivered: ["Waiting for the client", "The client is reviewing the episodes."],
        accepted: ["Completed", "The client accepted this delivery."],
        rejected: ["Sent back by the client", "Start rework: swap the rejected episodes, then deliver again."],
      }
    : {
        submitted: ["Submitted", "Our operators will pick up your request soon."],
        in_progress: ["Being prepared", "Our operators are assembling your episodes."],
        delivered: ["Ready for your review", "Keep, return or reject each episode in the list."],
        accepted: ["Completed", "You accepted this delivery. Thank you!"],
        rejected: ["Sent back for rework", "The team will replace what you rejected and deliver again."],
      };
  return texts[r.status];
}

function ActionBox({ request: r, staff, moving, clientReviewing, onMove }) {
  const [title, text] = explain(r, staff);
  const meta = STATUS[r.status];
  const Icon = meta.icon;
  const missing = r.episodes_requested - r.episodes_assigned;
  // The client decides through the review list, so no whole-delivery buttons for them here.
  const targets = clientReviewing ? [] : r.allowed_next;

  return (
    <div className="action-box">
      <div className="what">
        <div className={`ic tone-${meta.tone}`}><Icon size={16} aria-hidden="true" /></div>
        <div><h3>{title}</h3><p>{text}</p></div>
      </div>
      {targets.length > 0 && (
        <div className="actions">
          {targets.map((target) => {
            const action = actionFor(target, r.status);
            const blocked = target === "delivered" && missing > 0; // the server refuses too
            return (
              <Button key={target} kind={action.kind} icon={action.icon} busy={moving === target}
                disabled={Boolean(moving) || blocked} title={blocked ? `Assign ${missing} more episode(s) first` : undefined}
                onClick={() => onMove(target)}>
                {action.label}
              </Button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ConfirmDecision({ status, request, busy, onCancel, onConfirm }) {
  const accepting = status === "accepted";
  const action = actionFor(status, request.status);
  return (
    <Modal
      title={accepting ? "Accept this delivery?" : "Reject this delivery?"}
      description={accepting ? `You confirm the ${plural(request.episodes_assigned, "episode")} meet your needs.` : "Every episode goes back for rework."}
      icon={action.icon}
      tone={accepting ? "green" : "red"}
      onClose={onCancel}
      footer={<>
        <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <Button kind={action.kind} icon={action.icon} busy={busy} onClick={onConfirm}>{action.label}</Button>
      </>}
    />
  );
}

function Timeline({ history }) {
  return (
    <ol className="timeline">
      {[...history].reverse().map((h, index) => {
        const meta = STATUS[h.to_status];
        const Icon = meta.icon;
        return (
          <li key={index}>
            <div className={`t-icon tone-${meta.tone}`}><Icon aria-hidden="true" /></div>
            <div className="t-body">
              <div className="t-title">{h.from_status ? `${STATUS[h.from_status].label} → ${meta.label}` : "Request submitted"}</div>
              <div className="t-meta">{h.changed_by_name} · {formatDateTime(h.changed_at)}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
