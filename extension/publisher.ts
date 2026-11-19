import { createConnection } from "node:net";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { LightState } from "./state";

const project = fileURLToPath(new URL("../", import.meta.url));
const lastStarts = new Map<string, number>();
export type Update = { op: "update"; session: string; seq: number; state: LightState } |
  { op: "remove"; session: string; seq: number };

export function stateDirectory(): string {
  return process.env.PI_LIGHT_STATE_DIR || join(homedir(), ".local", "state", "pi-light");
}

function startBridge(directory: string): void {
  const now = performance.now();
  if (now - (lastStarts.get(directory) ?? -Infinity) < 10000) return;
  lastStarts.set(directory, now);
  const env: Record<string, string> = { PYTHONUNBUFFERED: "1" };
  for (const key of ["HOME", "PATH", "TMPDIR", "LANG", "LC_ALL"]) {
    if (process.env[key]) env[key] = process.env[key]!;
  }
  try {
    const child = spawn(join(project, ".venv", "bin", "python"),
      [join(project, "host", "bridge.py"), "serve", "--state-dir", directory],
      { detached: true, stdio: "ignore", env });
    child.on("error", () => { /* An absent optional indicator never fails an agent. */ });
    child.unref();
  } catch { /* The next managed heartbeat can reconnect. */ }
}

export function publish(message: Update, directory = stateDirectory()): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>();
  let settled = false;
  let incoming = "";
  const socket = createConnection({ path: join(directory, "bridge.sock") });
  const finish = () => {
    if (settled) return;
    settled = true;
    socket.destroy();
    resolve();
  };
  socket.setTimeout(700, finish);
  socket.once("connect", () => {
    try { socket.end(JSON.stringify(message) + "\n"); } catch { finish(); }
  });
  socket.on("data", (data) => {
    incoming += data.toString("utf8");
    if (incoming.length > 4096 || incoming.includes("\n")) finish();
  });
  socket.once("error", (error: NodeJS.ErrnoException) => {
    if (error.code === "ENOENT" || error.code === "ECONNREFUSED") startBridge(directory);
    finish();
  });
  socket.once("end", finish);
  socket.once("close", finish);
  return promise;
}

/** One coalescing queue per root session; no prompts or arguments are retained. */
export class Publisher {
  readonly session = `omp:${process.pid}:${randomUUID()}`;
  private sequence = 0;
  private sending = false;
  private closed = false;
  private pending: Update | undefined;
  private idle: Promise<void> = Promise.resolve();
  constructor(private send: (message: Update) => Promise<void> = publish) {}
  update(state: LightState): void {
    if (this.closed) return;
    this.pending = { op: "update", session: this.session, seq: ++this.sequence, state };
    void this.drain();
  }
  remove(): void {
    if (this.closed) return;
    this.closed = true;
    this.pending = { op: "remove", session: this.session, seq: ++this.sequence };
    void this.drain();
  }
  flush(): Promise<void> { return this.idle; }
  private async drain(): Promise<void> {
    if (this.sending) return;
    this.sending = true;
    const completion = Promise.withResolvers<void>();
    this.idle = completion.promise;
    try {
      while (this.pending) {
        const message = this.pending;
        this.pending = undefined;
        try { await this.send(message); } catch { /* Optional, failure-isolated transport. */ }
      }
    } finally {
      this.sending = false;
      completion.resolve();
    }
  }
}
