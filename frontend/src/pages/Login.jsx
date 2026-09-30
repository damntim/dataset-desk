import { ArrowRight, Eye, EyeOff, Layers, Lock, Mail, ShieldCheck, Sparkles, TriangleAlert, Zap } from "lucide-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Brand, ThemeButton } from "../components/Layout";
import { Button } from "../components/ui";
import { initials } from "../format";

// The seed accounts from seed/users.json, so reviewers can try each role in one click.
const DEMO_ACCOUNTS = [
  { name: "Ada Admin", role: "admin", email: "admin@example.com", password: "admin123" },
  { name: "Olu Operator", role: "operator", email: "ops1@example.com", password: "ops123" },
  { name: "Acme Robotics", role: "client", email: "client-a@example.com", password: "client123" },
  { name: "Beta Labs", role: "client", email: "client-b@example.com", password: "client123" },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (user) return <Navigate to={location.state?.from || "/"} replace />;

  async function signIn(emailValue, passwordValue) {
    setBusy(true);
    setError(null);
    try {
      await login(emailValue, passwordValue);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  function signInAsDemo(account) {
    setEmail(account.email);
    setPassword(account.password);
    signIn(account.email, account.password);
  }

  return (
    <div className="login">
      <section className="login-hero">
        <div className="blob one" />
        <div className="blob two" />
        <div className="blob three" />
        <Brand />

        <div className="hero-copy">
          <h1>
            Robot data, <span className="gradient-text">requested</span> and delivered.
          </h1>
          <p>
            Clients ask for episodes. Operators assemble them from real teleoperation recordings.
            Every step is tracked, from the first request to the final sign-off.
          </p>
          <div className="hero-features">
            <div><Layers aria-hidden="true" /> Clean episode imports, safe to run twice</div>
            <div><Zap aria-hidden="true" /> A clear workflow with a full history</div>
            <div><ShieldCheck aria-hidden="true" /> Every rule enforced on the server</div>
          </div>
        </div>

        <div className="hero-card" aria-hidden="true">
          <div className="hc-top">
            <span>Request #24 · Acme Robotics</span>
            <span className="badge">Delivered</span>
          </div>
          <div className="hc-task">200 × pick cup</div>
          <div className="progress"><div style={{ width: "100%" }} /></div>
          <div className="hc-steps">
            <span className="on" /><span className="on" /><span className="on" /><span />
          </div>
        </div>
      </section>

      <section className="login-panel">
        <div className="theme-float">
          <ThemeButton />
        </div>
        <form
          className="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            signIn(email, password);
          }}
        >
          <div>
            <h2>Welcome back</h2>
          </div>
          <p>Sign in to manage your dataset requests.</p>

          {error && (
            <div className="form-error" role="alert">
              <TriangleAlert size={18} aria-hidden="true" />
              {error}
            </div>
          )}

          <label className="field">
            <span>Email</span>
            <div className="input-icon">
              <Mail size={18} aria-hidden="true" />
              <input
                className="input"
                type="email"
                autoComplete="username"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </label>

          <label className="field">
            <span>Password</span>
            <div className="input-icon">
              <Lock size={18} aria-hidden="true" />
              <input
                className="input"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="icon-btn toggle-visibility"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>

          <Button type="submit" size="lg" busy={busy} className="btn-block">
            Sign in <ArrowRight size={18} aria-hidden="true" />
          </Button>

          <div className="demo">
            <div className="demo-title">
              <Sparkles size={14} aria-hidden="true" /> Demo accounts: one click to sign in
            </div>
            <div className="demo-grid">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  type="button"
                  key={account.email}
                  className="demo-btn"
                  onClick={() => signInAsDemo(account)}
                  disabled={busy}
                >
                  <div className="avatar sm">{initials(account.name)}</div>
                  <div>
                    <div className="dn">{account.name}</div>
                    <div className="dr">{account.role}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </form>
      </section>
    </div>
  );
}
