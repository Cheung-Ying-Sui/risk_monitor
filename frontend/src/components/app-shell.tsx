"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useAuth } from "@/components/auth-gate";

type NavigationSection = "sanctions-screening" | "vessel-tracking" | "insurance-management" | "maritime-intelligence";
type IconName = "vessel" | "shield" | "screen" | "alert" | "bell" | "chevron";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    vessel: <><path d="m12 3 6.5 16L12 16l-6.5 3L12 3Z"/><path d="M12 16v5"/></>,
    shield: <><path d="M12 3 20 6v5c0 5.1-3.3 8.4-8 10-4.7-1.6-8-4.9-8-10V6l8-3Z"/><path d="m9 12 2 2 4-4"/></>,
    screen: <><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8M12 18v3"/></>,
    alert: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
    chevron: <path d="m9 18 6-6-6-6"/>,
  };

  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const navigation: Array<{ label: string; icon: IconName; href: string; id?: NavigationSection }> = [
  { label: "保险管理", icon: "shield", href: "/insurance-management", id: "insurance-management" },
  { label: "制裁筛查", icon: "screen", href: "/sanctions-screening", id: "sanctions-screening" },
  { label: "船舶跟踪", icon: "vessel", href: "/", id: "vessel-tracking" },
  { label: "海事情报", icon: "alert", href: "/maritime-intelligence", id: "maritime-intelligence" },
];

interface AppShellProps {
  activeSection: NavigationSection;
  eyebrow?: string;
  context: string;
  children: ReactNode;
}

export function AppShell({ activeSection, eyebrow, context, children }: AppShellProps) {
  const { user, signOut } = useAuth();
  const [signOutError, setSignOutError] = useState("");
  const email = user?.email ?? "";
  const initials = email.slice(0, 2).toUpperCase() || "用户";

  async function handleSignOut() {
    try {
      await signOut();
    } catch {
      setSignOutError("退出登录失败，请重试。");
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand" aria-label="中化保险经纪">
          <span className="brand-logo-frame">
            <Image className="brand-logo" src="/branding/sinochem-capital-logo.png" width={1181} height={236} alt="" priority />
          </span>
          <span className="brand-copy"><strong>中化保险经纪</strong><small>海事智能平台</small></span>
        </div>
        <nav className="primary-nav" aria-label="主导航">
          <p className="nav-heading">平台功能</p>
          {navigation.map(item => {
            const active = item.id === activeSection;
            return (
              <Link className={`nav-item${active ? " active" : ""}`} href={item.href} key={item.label} aria-current={active ? "page" : undefined}>
                <Icon name={item.icon}/><span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer"><div className="system-status"><span className="status-dot"/><span><strong>所有系统运行正常</strong><small>实时服务状态</small></span></div><div className="profile"><div className="avatar">{initials}</div><span><strong>{email}</strong><small>已验证平台账号</small></span></div></div>
      </aside>
      <section className="workspace">
        <header className="topbar"><div className="page-context">{eyebrow && <><span className="eyebrow">{eyebrow}</span><span className="context-divider"/></>}<strong>{context}</strong></div><div className="topbar-actions"><button className="icon-button notification" type="button" aria-label="通知"><Icon name="bell" size={17}/><span/></button><button className="auth-sign-out" onClick={() => void handleSignOut()} type="button">退出登录</button><div className="utc-clock"><small>UTC</small><strong>14:32:08</strong></div></div>{signOutError && <p className="auth-sign-out-error" role="alert">{signOutError}</p>}</header>
        {children}
      </section>
    </main>
  );
}
