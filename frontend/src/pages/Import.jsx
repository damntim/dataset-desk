import { CloudUpload, FileSpreadsheet, Info, RotateCcw, TriangleAlert, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Button, StatTile } from "../components/ui";
import { plural } from "../format";
import { useToast } from "../toast";

// Friendly names for the reason codes the importer returns (app/importer.py).
const REASONS = {
  conflicting_duplicate: "Same id, different values",
  duplicate_in_file: "Duplicate row",
  missing_episode_id: "Missing episode id",
  invalid_episode_id: "Invalid episode id",
  missing_robot: "Missing robot",
  unknown_robot: "Unknown robot",
  missing_task_name: "Missing task",
  invalid_task_name: "Task name too long",
  invalid_date: "Unreadable date",
  future_date: "Date in the future",
  invalid_duration: "Bad duration",
  invalid_quality: "Bad quality",
  invalid_operator_name: "Operator name too long",
  malformed_row: "Malformed row",
  blank_line: "Blank line",
};

const formatBytes = (n) => (n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

export default function Import() {
  const toast = useToast();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  function choose(chosen) {
    if (!chosen) return;
    setFile(chosen);
    setReport(null);
    setError(null);
  }

  async function upload() {
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    setError(null);
    try {
      const result = await api("/episodes/import", { method: "POST", form });
      setReport(result);
      toast.success(
        result.imported > 0
          ? `${plural(result.imported, "episode")} imported`
          : "Nothing new: every valid row was already imported",
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="greet">Import episodes</div>
          <p>
            Upload the CSV export from the recording system. Rows are cleaned and checked, and every
            skipped row says why. It is safe to upload the same file again: nothing gets duplicated.
          </p>
        </div>
      </header>

      <section
        className={`dropzone ${dragging ? "over" : ""}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          choose(e.dataTransfer.files?.[0]);
        }}
        role="button"
        tabIndex={0}
        aria-label="Choose a CSV file"
      >
        <div className="dz-icon"><CloudUpload size={22} aria-hidden="true" /></div>
        <h3>{dragging ? "Drop it here" : "Drag your CSV here, or click to browse"}</h3>
        <p>Columns: episode_id, robot_id, task_name, recorded_at, duration_seconds, operator_name, quality · max 25 MB</p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          hidden
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = ""; // allow picking the same file again
          }}
        />
      </section>

      {file && (
        <section className="file-pill">
          <div className="fp-icon"><FileSpreadsheet size={22} aria-hidden="true" /></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="fp-name">{file.name}</div>
            <div className="muted" style={{ fontSize: "0.82rem" }}>{formatBytes(file.size)}</div>
          </div>
          <button className="icon-btn" onClick={() => setFile(null)} aria-label="Remove file" disabled={busy}>
            <X size={18} />
          </button>
          <Button icon={report ? RotateCcw : CloudUpload} busy={busy} onClick={upload}>
            {report ? "Import again" : "Import"}
          </Button>
        </section>
      )}

      {error && (
        <div className="form-error" role="alert"><TriangleAlert size={18} aria-hidden="true" /> {error}</div>
      )}

      {report && <Report report={report} />}
    </div>
  );
}

function Report({ report }) {
  const [reason, setReason] = useState(null);
  const reasons = Object.entries(report.skipped_by_reason).sort((a, b) => b[1] - a[1]);
  const rows = useMemo(
    () => report.skipped_details.filter((row) => !reason || row.reasons.some((r) => r.code === reason)),
    [report, reason],
  );
  const pct = (n) => (report.total_rows ? (n / report.total_rows) * 100 : 0);

  return (
    <>
      <section className="stats" aria-label="Import result">
        <StatTile tone="neutral" label="Rows read" value={report.total_rows.toLocaleString()} sub="in the file" />
        <StatTile tone="green" label="Imported" value={report.imported.toLocaleString()} sub="new episodes" />
        <StatTile tone="blue" label="Already existed" value={report.already_existed.toLocaleString()} sub="left unchanged" />
        <StatTile tone="amber" label="Skipped" value={report.skipped.toLocaleString()} sub="see reasons below" />
      </section>

      <section className="card card-pad" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="split-bar" role="img" aria-label="Share of rows imported, already existing and skipped">
          <div style={{ width: `${pct(report.imported)}%`, background: "var(--green)" }} />
          <div style={{ width: `${pct(report.already_existed)}%`, background: "var(--blue)" }} />
          <div style={{ width: `${pct(report.skipped)}%`, background: "var(--amber)" }} />
        </div>
        <div className="legend">
          <span><i className="swatch" style={{ background: "var(--green)" }} />Imported</span>
          <span><i className="swatch" style={{ background: "var(--blue)" }} />Already existed</span>
          <span><i className="swatch" style={{ background: "var(--amber)" }} />Skipped</span>
        </div>
        {report.already_existed > 0 && report.imported === 0 && (
          <div className="notice tone-blue">
            <Info size={18} aria-hidden="true" />
            Every valid row was already in the database, so nothing changed. That is the import being idempotent.
          </div>
        )}
      </section>

      {report.skipped > 0 && (
        <section className="card">
          <div className="card-head">
            <div className="title"><TriangleAlert size={20} aria-hidden="true" /><h2>Skipped rows</h2></div>
            <div className="segmented">
              <button className={`chip ${!reason ? "active" : ""}`} onClick={() => setReason(null)}>
                All <span className="count">{report.skipped}</span>
              </button>
              {reasons.map(([code, count]) => (
                <button key={code} className={`chip ${reason === code ? "active" : ""}`} onClick={() => setReason(code)}>
                  {REASONS[code] ?? code} <span className="count">{count}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="table-wrap">
            <table className="table responsive">
              <thead>
                <tr><th className="num">Line</th><th>Episode</th><th>Why it was skipped</th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.line}>
                    <td data-label="Line" className="num mono">{row.line}</td>
                    <td data-label="Episode" className="mono cell-strong">{row.episode_id ?? "—"}</td>
                    <td data-label="Reason" className="full" style={{ textAlign: "left" }}>
                      {row.reasons.map((r) => (
                        <div key={r.code}>
                          <span className="badge tone-amber" style={{ marginRight: 8 }}>{REASONS[r.code] ?? r.code}</span>
                          <span className="muted" style={{ fontSize: "0.84rem" }}>{r.message}</span>
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {report.details_truncated && (
            <p className="muted" style={{ padding: "12px 22px" }}>Only the first 500 rows are listed. The counts above are exact.</p>
          )}
        </section>
      )}
    </>
  );
}
