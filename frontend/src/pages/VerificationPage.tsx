import { Link } from "react-router-dom";

export function VerificationPage() {
  return (
    <main className="auth-page auth-page-single">
      <section className="auth-card auth-state-card">
        <div className="auth-brand auth-brand-dark"><span className="brand-mark" aria-hidden="true">PB</span><strong>Pacific BioArchive</strong></div>
        <span className="state-icon" aria-hidden="true">✉</span>
        <p className="panel-kicker">Email verification</p>
        <h1>Check your email</h1>
        <p>Cognito sends and validates the verification code in its hosted registration flow.</p>
        <Link className="button auth-link" to="/login">Return to sign in</Link>
      </section>
    </main>
  );
}
