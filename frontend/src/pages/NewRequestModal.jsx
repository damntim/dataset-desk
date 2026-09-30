import { ClipboardPlus, Send } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { Button, Modal } from "../components/ui";
import { useToast } from "../toast";
import { addDaysIso, todayIso } from "../format";

// Common tasks, as suggestions only: the client may type anything.
const SUGGESTED_TASKS = ["pick cup", "place cup on shelf", "open drawer", "fold towel", "pour water", "stack blocks", "wipe table"];

export default function NewRequestModal({ onClose, onCreated }) {
  const toast = useToast();
  const [form, setForm] = useState({
    task_name: "",
    episodes_requested: 100,
    deadline: addDaysIso(todayIso(), 30),
    notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api("/requests", {
        method: "POST",
        body: {
          task_name: form.task_name,
          episodes_requested: Number(form.episodes_requested),
          deadline: form.deadline,
          notes: form.notes.trim() || null,
        },
      });
      toast.success(`Request #${created.id} submitted`);
      onCreated(created);
    } catch (err) {
      setError(err.message); // the server's own validation message
      setBusy(false);
    }
  }

  return (
    <Modal
      title="New dataset request"
      description="Tell our operators what you need. You can follow every step from here."
      icon={ClipboardPlus}
      onClose={onClose}
    >
      <form id="new-request" onSubmit={submit} style={{ display: "contents" }}>
        {error && <div className="form-error" role="alert">{error}</div>}
        <label className="field">
          <span>Task</span>
          <input
            className="input"
            list="task-suggestions"
            placeholder="e.g. pick cup"
            value={form.task_name}
            onChange={update("task_name")}
            maxLength={255}
            required
            autoFocus
          />
          <datalist id="task-suggestions">
            {SUGGESTED_TASKS.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </label>
        <div className="form-row">
          <label className="field">
            <span>Episodes needed</span>
            <input
              className="input"
              type="number"
              min={1}
              max={100000}
              value={form.episodes_requested}
              onChange={update("episodes_requested")}
              required
            />
          </label>
          <label className="field">
            <span>Deadline</span>
            <input
              className="input"
              type="date"
              min={todayIso()}
              value={form.deadline}
              onChange={update("deadline")}
              required
            />
          </label>
        </div>
        <label className="field">
          <span>
            Notes <span className="hint">(optional)</span>
          </span>
          <textarea
            className="textarea"
            placeholder="Lighting, robot type, anything that matters to you…"
            value={form.notes}
            onChange={update("notes")}
            maxLength={2000}
          />
        </label>
        <div className="modal-foot" style={{ padding: 0 }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <Button type="submit" icon={Send} busy={busy}>
            Submit request
          </Button>
        </div>
      </form>
    </Modal>
  );
}
