import { EventEmitter } from "node:events";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import path from "node:path";
import { app } from "electron";

interface RpcResponse {
  id?: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
  event?: string;
  payload?: unknown;
}

export class PythonSidecar extends EventEmitter {
  private process: ChildProcessWithoutNullStreams | null = null;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (error: Error) => void }
  >();

  start(): void {
    if (this.process) {
      return;
    }

    const userData = app.getPath("userData");
    const resourcesPath = process.resourcesPath;
    const packagedExecutable = path.join(
      resourcesPath,
      "backend",
      process.platform === "win32" ? "syncrotify-backend.exe" : "syncrotify-backend"
    );
    const command = app.isPackaged ? packagedExecutable : process.env.PYTHON ?? "python";
    const args = app.isPackaged
      ? []
      : ["-m", "syncrotify_backend.desktop_rpc"];

    this.process = spawn(command, args, {
      cwd: app.isPackaged ? resourcesPath : app.getAppPath(),
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        SYNCROTIFY_USER_DATA: userData,
        SYNCROTIFY_RESOURCE_PATH: resourcesPath,
        SYNCROTIFY_BIN_PATH: path.join(resourcesPath, "bin"),
        PYTHONUNBUFFERED: "1"
      }
    });

    const lines = createInterface({ input: this.process.stdout });
    lines.on("line", (line) => this.handleLine(line));
    this.process.stderr.on("data", (chunk) => {
      this.emit("diagnostic", chunk.toString());
    });
    this.process.on("error", (error) => {
      for (const request of this.pending.values()) {
        request.reject(error);
      }
      this.pending.clear();
      this.process = null;
      this.emit("diagnostic", error.message);
    });
    this.process.on("exit", (code) => {
      const error = new Error(`Syncrotify backend exited with code ${code ?? "unknown"}`);
      for (const request of this.pending.values()) {
        request.reject(error);
      }
      this.pending.clear();
      this.process = null;
      this.emit("exit", code);
    });
  }

  async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    this.start();
    const id = this.nextId++;
    const payload = JSON.stringify({ id, method, params });

    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, {
        resolve: (value) => resolve(value as T),
        reject
      });
      this.process?.stdin.write(`${payload}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  stop(): void {
    this.process?.kill();
    this.process = null;
  }

  private handleLine(line: string): void {
    let message: RpcResponse;
    try {
      message = JSON.parse(line) as RpcResponse;
    } catch {
      this.emit("diagnostic", `Invalid backend message: ${line}`);
      return;
    }

    if (message.event) {
      this.emit("event", { type: message.event, payload: message.payload });
      return;
    }

    if (message.id === undefined) {
      return;
    }

    const pending = this.pending.get(message.id);
    if (!pending) {
      return;
    }
    this.pending.delete(message.id);

    if (message.error) {
      pending.reject(new Error(message.error.message));
    } else {
      pending.resolve(message.result);
    }
  }
}
