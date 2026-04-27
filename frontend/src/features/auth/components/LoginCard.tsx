import { useState } from "react";

import { useAppStore } from "../../app/store";

type AuthMode = "login" | "register";

export function LoginCard() {
  const login = useAppStore((state) => state.login);
  const register = useAppStore((state) => state.register);
  const mutating = useAppStore((state) => state.mutating);
  const error = useAppStore((state) => state.error);
  const clearError = useAppStore((state) => state.clearError);

  const [mode, setMode] = useState<AuthMode>("login");
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearError();
    try {
      if (mode === "login") {
        await login(username.trim(), password);
        return;
      }
      await register(displayName.trim(), username.trim(), password);
    } catch {
      // store 已保存错误信息，UI 侧展示即可
    }
  }

  return (
    <section className="auth-card">
      <div className="auth-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          className={mode === "login" ? "active" : ""}
          onClick={() => setMode("login")}
        >
          登录
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          className={mode === "register" ? "active" : ""}
          onClick={() => setMode("register")}
        >
          注册
        </button>
      </div>

      <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
        {mode === "register" ? (
          <div>
            <label htmlFor="display-name">昵称</label>
            <input
              id="display-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="用于在会话中的显示名"
              autoComplete="nickname"
            />
          </div>
        ) : null}

        <div>
          <label htmlFor="username">账号</label>
          <input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="字母 · 数字 · 下划线"
            autoComplete="username"
          />
        </div>

        <div>
          <label htmlFor="password">密码</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="不少于 8 位"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </div>

        {error ? <p className="form-error">{error}</p> : null}

        <button type="submit" className="primary-button" disabled={mutating}>
          {mutating ? "提交中…" : mode === "login" ? "登录" : "注册并进入"}
        </button>
      </form>
    </section>
  );
}
