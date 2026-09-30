// Small building blocks used on many pages.
import { LoaderCircle, X } from "lucide-react";
import { useEffect } from "react";
import { QUALITY, STATUS } from "../format";

export function StatusBadge({ status }) {
  const meta = STATUS[status] ?? { label: status, tone: "neutral" };
  const Icon = meta.icon;
  return (
    <span className={`badge tone-${meta.tone}`}>
      {Icon && <Icon aria-hidden="true" />}
      {meta.label}
    </span>
  );
}

export function QualityBadge({ quality }) {
  const meta = QUALITY[quality] ?? { label: quality, tone: "neutral" };
  return (
    <span className={`badge tone-${meta.tone}`}>
      <span className="dot" aria-hidden="true" />
      {meta.label}
    </span>
  );
}

export function Spinner({ size = 18 }) {
  return <LoaderCircle className="spinner" size={size} aria-hidden="true" />;
}

/** A button that shows a spinner and blocks double clicks while `busy`. */
export function Button({ kind = "primary", size, icon: Icon, busy, children, className = "", ...rest }) {
  const classes = ["btn", `btn-${kind}`, size && `btn-${size}`, className].filter(Boolean).join(" ");
  return (
    <button className={classes} disabled={busy || rest.disabled} {...rest}>
      {busy ? <Spinner /> : Icon && <Icon size={18} aria-hidden="true" />}
      {children}
    </button>
  );
}

export function ProgressBar({ value, max }) {
  const percent = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="progress-label">
        <span>Episodes</span>
        <span>
          <strong>{value}</strong> / {max}
        </span>
      </div>
      <div
        className={`progress ${value >= max ? "complete" : ""}`}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label="Episodes assigned"
      >
        <div style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

/** Dashboard tile: small label on top, big coloured number, sub line, short colour bar.
 *  Pass onClick to make it a filter button. */
export function StatTile({ label, value, sub, subTone, tone = "neutral", onClick, selected, loading }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      className={`stat tone-text-${tone} ${selected ? "selected" : ""}`}
      onClick={onClick}
      aria-pressed={onClick ? Boolean(selected) : undefined}
    >
      <div className="stat-label">{label}</div>
      <div className="stat-value">{loading ? "–" : value ?? "—"}</div>
      {sub && <div className={`stat-sub ${subTone ?? ""}`}>{sub}</div>}
      <span className="stat-bar" aria-hidden="true" />
    </Tag>
  );
}

export function ProgressRing({ value, max, size = 84, stroke = 9 }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const ratio = max > 0 ? Math.min(1, value / max) : 0;
  const done = value >= max;
  const gradientId = done ? "ring-done" : "ring-grad";
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden="true">
        <defs>
          <linearGradient id="ring-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#6f5cff" />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
          <linearGradient id="ring-done" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#1baf7a" />
            <stop offset="1" stopColor="#4fd39b" />
          </linearGradient>
        </defs>
        <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} />
        <circle
          className="ring-value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
        />
      </svg>
      <div className="ring-text">
        <strong>{Math.round(ratio * 100)}%</strong>
        <span>
          {value} of {max}
        </span>
      </div>
    </div>
  );
}

export function Modal({ title, description, icon: Icon, tone = "violet", onClose, children, footer }) {
  // Escape closes the dialog.
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-head">
          {Icon && (
            <div className={`modal-icon tone-${tone}`}>
              <Icon size={22} aria-hidden="true" />
            </div>
          )}
          <div style={{ flex: 1 }}>
            <h2 id="modal-title">{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {children && <div className="modal-body">{children}</div>}
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={28} aria-hidden="true" />
      </div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorNotice({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="notice tone-red" role="alert">
      <span style={{ flex: 1 }}>{error.message}</span>
      {onRetry && (
        <button className="btn btn-sm btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
