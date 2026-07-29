import { FormEvent } from "react";
import { createPortal } from "react-dom";
import { formatBrandTitle } from "../formatBrandTitle";

interface Props {
  onSubmit: (username: string, password: string) => void;
  error?: string | null;
  projectName?: string | null;
  loading?: boolean;
}

export function UserIdModal({ onSubmit, error, projectName, loading }: Props) {
  const title = formatBrandTitle(projectName ?? "agent");

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (loading) return;
    const form = new FormData(e.currentTarget);
    const username = String(form.get("username") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (!username || !password) return;
    onSubmit(username, password);
  }

  return createPortal(
    <div className="auth-screen">
      <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="login-title">
        <form className="modal" onSubmit={handleSubmit}>
          <h2 id="login-title">{title}</h2>
          <p>Cognito 계정으로 로그인하세요.</p>
          {error && <p className="modal-error">{error}</p>}
          <label className="modal-label" htmlFor="login-username">
            ID
          </label>
          <input
            id="login-username"
            name="username"
            placeholder="예: admin"
            autoComplete="username"
            autoFocus
            required
            disabled={loading}
          />
          <label className="modal-label" htmlFor="login-password">
            Password
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            placeholder="비밀번호"
            autoComplete="current-password"
            required
            disabled={loading}
          />
          <div className="modal-actions">
            <button type="submit" className="send-btn" disabled={loading}>
              {loading ? "로그인 중…" : "로그인"}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
