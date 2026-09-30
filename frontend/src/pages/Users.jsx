import { UserPlus, Users as UsersIcon } from "lucide-react";
import { useState } from "react";
import { api, useApi } from "../api";
import { useAuth } from "../auth";
import { Button, ErrorNotice, Modal } from "../components/ui";
import { initials } from "../format";
import { useToast } from "../toast";

const ROLES = ["client", "operator", "admin"];

export default function Users() {
  const { user: me } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useApi("/users");
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(null);

  async function change(user, changes, message) {
    setSaving(user.id);
    try {
      await api(`/users/${user.id}`, { method: "PATCH", body: changes });
      toast.success(message);
      reload();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="greet">People and roles</div>
          <p>Create accounts, change roles, and switch off access. Changes apply immediately, even to people already signed in.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setAdding(true)}>
          <UserPlus size={16} aria-hidden="true" /> Add user
        </button>
      </header>

      <ErrorNotice error={error} onRetry={reload} />

      <section className="card">
        <div className="card-head">
          <div className="title"><UsersIcon size={20} aria-hidden="true" /><h2>All users</h2></div>
          {data && <span className="badge tone-neutral">{data.length}</span>}
        </div>
        {loading && !data ? (
          <div className="card-body"><div className="skeleton" style={{ height: 240 }} /></div>
        ) : (
          <div className="table-wrap">
            <table className="table responsive">
              <thead>
                <tr><th>Person</th><th>Organisation</th><th>Role</th><th>Access</th></tr>
              </thead>
              <tbody>
                {(data ?? []).map((u) => {
                  const isMe = u.id === me.id;
                  return (
                    <tr key={u.id} className={u.is_active ? "" : "disabled"}>
                      <td data-label="Person" className="cell-title">
                        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                          <div className="avatar sm">{initials(u.name)}</div>
                          <div style={{ textAlign: "left", minWidth: 0 }}>
                            <div className="cell-strong">{u.name} {isMe && <span className="role-pill">you</span>}</div>
                            <div className="cell-sub" style={{ overflowWrap: "anywhere" }}>{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td data-label="Organisation">{u.organisation ?? <span className="muted">—</span>}</td>
                      <td data-label="Role">
                        <select
                          className="select"
                          style={{ height: 30, width: 130 }}
                          value={u.role}
                          disabled={isMe || saving === u.id}
                          title={isMe ? "You cannot change your own role" : undefined}
                          onChange={(e) => change(u, { role: e.target.value }, `${u.name} is now ${e.target.value}`)}
                          aria-label={`Role of ${u.name}`}
                        >
                          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                        </select>
                      </td>
                      <td data-label="Access">
                        <button
                          className="switch"
                          role="switch"
                          aria-checked={u.is_active}
                          aria-label={`${u.is_active ? "Deactivate" : "Activate"} ${u.name}`}
                          disabled={isMe || saving === u.id}
                          onClick={() => change(u, { is_active: !u.is_active }, `${u.name} ${u.is_active ? "deactivated" : "activated"}`)}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {adding && (
        <AddUserModal
          onClose={() => setAdding(false)}
          onCreated={() => {
            setAdding(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

function AddUserModal({ onClose, onCreated }) {
  const toast = useToast();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "client", organisation: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api("/users", {
        method: "POST",
        body: { ...form, organisation: form.organisation.trim() || null },
      });
      toast.success(`${created.name} can now sign in`);
      onCreated();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Add a user" description="They sign in with this email and password." icon={UserPlus} onClose={onClose}>
      <form onSubmit={submit} style={{ display: "contents" }}>
        {error && <div className="form-error" role="alert">{error}</div>}
        <div className="form-row">
          <label className="field"><span>Name</span>
            <input className="input" value={form.name} onChange={update("name")} required autoFocus maxLength={255} />
          </label>
          <label className="field"><span>Role</span>
            <select className="select" value={form.role} onChange={update("role")}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
        </div>
        <label className="field"><span>Email</span>
          <input className="input" type="email" value={form.email} onChange={update("email")} required />
        </label>
        <label className="field"><span>Password <span className="hint">(8 characters or more)</span></span>
          <input className="input" type="password" value={form.password} onChange={update("password")} minLength={8} required autoComplete="new-password" />
        </label>
        {form.role === "client" && (
          <label className="field"><span>Organisation</span>
            <input className="input" value={form.organisation} onChange={update("organisation")} maxLength={255} placeholder="e.g. Acme Robotics" />
          </label>
        )}
        <div className="modal-foot" style={{ padding: 0 }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <Button type="submit" icon={UserPlus} busy={busy}>Create user</Button>
        </div>
      </form>
    </Modal>
  );
}
