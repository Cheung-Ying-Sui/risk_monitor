"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createContext, useContext } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseBrowserClient, isSupabaseAuthConfigured } from "@/lib/supabase";
import "./auth-gate.css";

interface AuthContextValue {
  user: User | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthGate.");
  return context;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isSupabaseAuthConfigured);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isSupabaseAuthConfigured) {
      return;
    }

    const client = getSupabaseBrowserClient();
    const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });
    void client.auth.getSession().then(({ data, error: sessionError }) => {
      if (sessionError) setError("无法读取登录状态，请刷新页面重试。");
      setSession(data.session);
      setLoading(false);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const { error: signInError } = await getSupabaseBrowserClient().auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (signInError) throw signInError;
    } catch {
      setError("登录失败，请检查邮箱和密码，或联系管理员确认账号权限。");
    } finally {
      setSubmitting(false);
    }
  }

  async function signOut() {
    const { error: signOutError } = await getSupabaseBrowserClient().auth.signOut();
    if (signOutError) throw signOutError;
  }

  if (loading) {
    return <main className="auth-screen"><p className="auth-loading">正在验证登录状态…</p></main>;
  }

  if (!isSupabaseAuthConfigured) {
    return (
      <main className="auth-screen">
        <section className="auth-card" role="alert">
          <span className="auth-eyebrow">SYSTEM CONFIGURATION</span>
          <h1>登录服务未配置</h1>
          <p>请在部署环境中设置 Supabase 项目地址和公开客户端密钥，再重新部署前端。</p>
        </section>
      </main>
    );
  }

  if (!session?.user) {
    return (
      <main className="auth-screen">
        <form className="auth-card" onSubmit={signIn}>
          <span className="auth-eyebrow">SINOCHEM MARITIME RISK PLATFORM</span>
          <h1>登录海事智能平台</h1>
          <p>请使用管理员分配的平台账号。未授权账号无法访问业务数据。</p>
          <label htmlFor="auth-email">邮箱</label>
          <input
            autoComplete="username"
            id="auth-email"
            onChange={event => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label htmlFor="auth-password">密码</label>
          <input
            autoComplete="current-password"
            id="auth-password"
            onChange={event => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button disabled={submitting} type="submit">
            {submitting ? "正在登录…" : "登录"}
          </button>
          <small>账号由平台管理员创建和授权。</small>
        </form>
      </main>
    );
  }

  return (
    <AuthContext.Provider value={{ user: session.user, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
