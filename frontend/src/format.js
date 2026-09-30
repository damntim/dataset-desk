// Labels, icons and colours for statuses, plus date and duration formatting.
import {
  BadgeCheck,
  CircleX,
  PackageCheck,
  Play,
  RotateCcw,
  Send,
  ThumbsDown,
  ThumbsUp,
  Wrench,
} from "lucide-react";

// Every status always shows an icon AND a label, never colour alone.
export const STATUS = {
  submitted: { label: "Submitted", icon: Send, tone: "blue" },
  in_progress: { label: "In progress", icon: Wrench, tone: "amber" },
  delivered: { label: "Delivered", icon: PackageCheck, tone: "violet" },
  accepted: { label: "Accepted", icon: BadgeCheck, tone: "green" },
  rejected: { label: "Rejected", icon: CircleX, tone: "red" },
};
export const STATUS_ORDER = ["submitted", "in_progress", "delivered", "accepted", "rejected"];

// The button for moving TO a status. The server decides which moves are allowed
// (request.allowed_next); this only decides how the button looks.
export function actionFor(target, current) {
  switch (target) {
    case "in_progress":
      return current === "rejected"
        ? { label: "Start rework", icon: RotateCcw, kind: "primary" }
        : { label: "Start work", icon: Play, kind: "primary" };
    case "delivered":
      return { label: "Mark as delivered", icon: PackageCheck, kind: "primary" };
    case "accepted":
      return { label: "Accept delivery", icon: ThumbsUp, kind: "success" };
    case "rejected":
      return { label: "Reject delivery", icon: ThumbsDown, kind: "danger" };
    default:
      return { label: target, icon: Play, kind: "primary" };
  }
}

export const QUALITY = {
  good: { label: "Good", tone: "green" },
  usable: { label: "Usable", tone: "amber" },
  bad: { label: "Bad", tone: "red" },
};

const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const shortDayFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", timeZone: "UTC" });

// "2026-10-20" is a calendar day: build it at local midnight so it never shifts a day.
export function parseDay(isoDay) {
  const [y, m, d] = isoDay.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const formatDay = (isoDay) => dateFmt.format(parseDay(isoDay));
export const formatDateTime = (iso) => dateTimeFmt.format(new Date(iso));
export const formatShortUtcDay = (isoDay) => shortDayFmt.format(new Date(`${isoDay}T00:00:00Z`));

export function todayIso() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function addDaysIso(isoDay, days) {
  const d = parseDay(isoDay);
  d.setDate(d.getDate() + days);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** { text: "Due in 12 days", tone: "neutral" | "amber" | "red" } */
export function deadlineInfo(isoDay, status) {
  const days = Math.round((parseDay(isoDay) - parseDay(todayIso())) / 86_400_000);
  if (status === "accepted") return { text: `Due ${formatDay(isoDay)}`, tone: "neutral" };
  if (days < 0) return { text: `Overdue by ${-days} day${days === -1 ? "" : "s"}`, tone: "red" };
  if (days === 0) return { text: "Due today", tone: "amber" };
  if (days <= 7) return { text: `Due in ${days} day${days === 1 ? "" : "s"}`, tone: "amber" };
  return { text: `Due in ${days} days`, tone: "neutral" };
}

/** 93784 -> "1d 2h", 5400 -> "1h 30m", 45 -> "45s" */
export function humanDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return h ? `${d}d ${h}h` : `${d}d`;
  if (h) return m ? `${h}h ${m}m` : `${h}h`;
  if (m) return `${m}m`;
  return `${s}s`;
}

export const initials = (name = "") =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") || "?";

export const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
