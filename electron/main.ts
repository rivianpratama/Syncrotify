import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  shell,
  Tray
} from "electron";
import type { AppConfig, BootstrapState, DeviceInfo } from "../src/types.js";
import { PythonSidecar } from "./python-sidecar.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sidecar = new PythonSidecar();
let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let quitting = false;
let closeBehavior: AppConfig["closeBehavior"] = "tray";

if (process.env.PORTABLE_EXECUTABLE_DIR) {
  app.setPath(
    "userData",
    path.join(process.env.PORTABLE_EXECUTABLE_DIR, "SyncrotifyData")
  );
}

function rendererUrl(): string {
  return (
    process.env.VITE_DEV_SERVER_URL ??
    `file://${path.join(__dirname, "../../dist/index.html")}`
  );
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1536,
    height: 1024,
    minWidth: 1050,
    minHeight: 720,
    backgroundColor: "#0d1118",
    show: false,
    title: "Syncrotify",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true
    }
  });

  void mainWindow.loadURL(rendererUrl());
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.on("close", (event) => {
    if (!quitting && closeBehavior === "tray") {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createTray(): void {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, "icon.png")
    : path.join(app.getAppPath(), "assets", "icon.png");
  const icon = nativeImage.createFromPath(iconPath).resize({ width: 18, height: 18 });
  tray = new Tray(icon);
  tray.setToolTip("Syncrotify");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Syncrotify", click: () => showWindow() },
      { label: "Sync now", click: () => void sidecar.call("sync.start") },
      { label: "Stop sync", click: () => void sidecar.call("sync.stop") },
      { type: "separator" },
      {
        label: "Quit",
        click: () => {
          quitting = true;
          app.quit();
        }
      }
    ])
  );
  tray.on("double-click", showWindow);
}

function showWindow(): void {
  if (!mainWindow) {
    createWindow();
  }
  mainWindow?.show();
  mainWindow?.focus();
}

function registerIpc(): void {
  ipcMain.handle("app:bootstrap", async (): Promise<BootstrapState> => {
    const state = await sidecar.call<BootstrapState>("app.bootstrap", {
      platform: process.platform,
      version: app.getVersion()
    });
    closeBehavior = state.config.closeBehavior;
    return state;
  });
  ipcMain.handle("config:save", async (_event, config: AppConfig) => {
    const saved = await sidecar.call<AppConfig>("config.save", { config });
    closeBehavior = saved.closeBehavior;
    app.setLoginItemSettings({ openAtLogin: saved.launchAtLogin });
    return saved;
  });
  ipcMain.handle("dialog:directory", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openDirectory", "createDirectory"]
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle("sync:start", () => sidecar.call("sync.start"));
  ipcMain.handle("sync:stop", () => sidecar.call("sync.stop"));
  ipcMain.handle("sync:approve", () => sidecar.call("sync.approve"));
  ipcMain.handle("devices:refresh", () => sidecar.call<DeviceInfo[]>("devices.refresh"));
  ipcMain.handle("devices:eject", (_event, deviceId: string) =>
    sidecar.call("devices.eject", { deviceId })
  );
  ipcMain.handle("app:launch-at-login", (_event, enabled: boolean) => {
    app.setLoginItemSettings({ openAtLogin: enabled });
  });
  ipcMain.handle("auth:login", () => sidecar.call("auth.login"));
  ipcMain.handle("auth:import", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openFile"],
      filters: [
        { name: "Authentication files", extensions: ["json", "txt"] }
      ]
    });
    if (result.canceled) {
      return { connected: false };
    }
    return sidecar.call("auth.import", { path: result.filePaths[0] });
  });
  ipcMain.handle("auth:logout", () => sidecar.call("auth.logout"));
  ipcMain.handle("app:show", () => showWindow());
  ipcMain.handle("app:quit", () => {
    quitting = true;
    app.quit();
  });
}

app.whenReady().then(() => {
  registerIpc();
  sidecar.start();
  sidecar.on("event", (event) => {
    mainWindow?.webContents.send("backend:event", event);
  });
  createWindow();
  createTray();
});

app.on("activate", showWindow);
app.on("before-quit", () => {
  quitting = true;
  sidecar.stop();
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin" && closeBehavior === "quit") {
    app.quit();
  }
});
