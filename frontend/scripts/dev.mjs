import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectDirectory = path.resolve(frontendDirectory, "..");
const python = path.join(projectDirectory, ".venv", "bin", "python");
const next = path.join(frontendDirectory, "node_modules", "next", "dist", "bin", "next");
const children = new Set();
let stopping = false;

function start(command, args, cwd) {
  const child = spawn(command, args, { cwd, stdio: "inherit" });
  children.add(child);
  child.once("exit", code => {
    children.delete(child);
    if (!stopping && code !== 0) {
      console.error(`\n开发服务异常退出（状态码 ${code ?? "未知"}）。`);
      stop(code ?? 1);
    }
  });
  return child;
}

function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill("SIGTERM");
  setTimeout(() => process.exit(exitCode), 250).unref();
}

async function apiIsRunning() {
  try {
    const response = await fetch("http://127.0.0.1:8000/health", { signal: AbortSignal.timeout(800) });
    return response.ok;
  } catch {
    return false;
  }
}

process.once("SIGINT", () => stop(0));
process.once("SIGTERM", () => stop(0));

if (await apiIsRunning()) {
  console.log("检测到 FastAPI 已在 8000 端口运行，将直接复用。\n");
} else {
  console.log("正在启动 FastAPI（http://127.0.0.1:8000）…\n");
  start(python, ["-m", "uvicorn", "api.main:app", "--app-dir", projectDirectory, "--port", "8000"], projectDirectory);
}

console.log("正在启动 Next.js（http://localhost:3000）…\n");
start(process.execPath, [next, "dev"], frontendDirectory);
