"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createContext, useContext } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseBrowserClient, isSupabaseAuthConfigured } from "@/lib/supabase";
import "./auth-gate.css";

const TEMPORARY_ACCESS_DURATION_MS = 7 * 24 * 60 * 60 * 1000;

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
  const [registering, setRegistering] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

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

  useEffect(() => {
    const user = session?.user;
    if (!user || user.user_metadata.temporary_platform_access !== true) return;

    const createdAt = Date.parse(user.created_at);
    const expiresAt = Number.isFinite(createdAt)
      ? createdAt + TEMPORARY_ACCESS_DURATION_MS
      : Date.now();

    async function expireTemporarySession() {
      const { error: signOutError } = await getSupabaseBrowserClient().auth.signOut();
      setSession(null);
      setError(
        signOutError
          ? "临时访问期限已结束，自动退出失败；请刷新页面后联系平台管理员。"
          : "临时访问期限已结束，请联系平台管理员。",
      );
    }

    const delay = expiresAt - Date.now();
    if (delay <= 0) {
      void expireTemporarySession();
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void expireTemporarySession();
    }, delay);
    return () => window.clearTimeout(timeoutId);
  }, [session]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setNotice("");
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

  async function signUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const { data, error: signUpError } = await getSupabaseBrowserClient().auth.signUp({
        email: email.trim(),
        password,
        options: { data: { temporary_platform_access: true } },
      });
      if (signUpError) throw signUpError;
      if (!data.session) {
        setNotice("注册已完成，但当前认证配置要求额外验证；请联系平台管理员。");
      } else {
        setNotice("注册成功，已开通 7 天只读访问权限。");
      }
    } catch {
      setError("注册失败，请检查邮箱和密码，或尝试使用其他邮箱。");
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
        <form className="auth-card" onSubmit={registering ? signUp : signIn}>
          <span className="auth-eyebrow">SINOCHEM MARITIME RISK PLATFORM</span>
          <h1>{registering ? "注册临时访问账号" : "登录海事智能平台"}</h1>
          <p>
            {registering
              ? "注册后可只读访问真实业务数据 7 天；不可创建或修改业务记录。"
              : "使用已注册的平台账号登录。"}
          </p>
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
            autoComplete={registering ? "new-password" : "current-password"}
            id="auth-password"
            minLength={8}
            onChange={event => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          {error && <p className="auth-error" role="alert">{error}</p>}
          {notice && <p className="auth-notice" role="status">{notice}</p>}
          <button disabled={submitting} type="submit">
            {submitting ? "请稍候…" : registering ? "注册并开始访问" : "登录"}
          </button>
          <button
            className="auth-mode-toggle"
            disabled={submitting}
            onClick={() => {
              setRegistering(!registering);
              setError("");
              setNotice("");
            }}
            type="button"
          >
            {registering ? "已有账号？返回登录" : "没有账号？注册 7 天临时账号"}
          </button>
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
