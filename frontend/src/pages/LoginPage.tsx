import { Navigate } from "react-router-dom";

import { LoginCard } from "../features/auth/components/LoginCard";
import { useAppStore } from "../features/app/store";

export function LoginPage() {
  const authStatus = useAppStore((state) => state.authStatus);

  if (authStatus === "authenticated") {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="login-shell">
      <section className="login-hero">
        <div className="login-hero-top">
          <span className="eyebrow">漆语 · LacquerTutor</span>
        </div>

        <div className="login-hero-mid">
          <h1>
            漆艺非遗教学的<span className="accent">全流程智能体</span>。
          </h1>
          <p>
            服务漆艺非遗教学的工坊导学智能体。基于专业知识库、工艺规范与安全管控，覆盖课前预习、课中互动、课后巩固三个教学阶段。
          </p>
        </div>

        <div className="login-hero-foot">
          <span className="dot" aria-hidden />
          <span>课前 · 课中 · 课后</span>
        </div>
      </section>

      <LoginCard />
    </main>
  );
}
