"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase";

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const { data, error } = await getSupabaseBrowserClient().auth.getSession();
  if (error) throw new Error("无法读取登录状态，请重新登录。");
  if (!data.session?.access_token) throw new Error("登录状态已失效，请重新登录。");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${data.session.access_token}`);
  return fetch(input, { ...init, headers });
}
