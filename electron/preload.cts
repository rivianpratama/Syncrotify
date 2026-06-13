import { contextBridge, ipcRenderer } from "electron";
import type {
  AppConfig,
  BackendEvent,
  BootstrapState,
  DeviceInfo,
  SyncrotifyApi
} from "../src/types.js" with { "resolution-mode": "import" };

const api: SyncrotifyApi = {
  bootstrap: () => ipcRenderer.invoke("app:bootstrap") as Promise<BootstrapState>,
  saveConfig: (config: AppConfig) =>
    ipcRenderer.invoke("config:save", config) as Promise<AppConfig>,
  chooseDirectory: () => ipcRenderer.invoke("dialog:directory") as Promise<string | null>,
  startSync: () => ipcRenderer.invoke("sync:start") as Promise<{ accepted: boolean }>,
  stopSync: () => ipcRenderer.invoke("sync:stop") as Promise<void>,
  approveSync: () => ipcRenderer.invoke("sync:approve") as Promise<void>,
  refreshDevices: () => ipcRenderer.invoke("devices:refresh") as Promise<DeviceInfo[]>,
  ejectDevice: (deviceId: string) =>
    ipcRenderer.invoke("devices:eject", deviceId) as Promise<void>,
  setLaunchAtLogin: (enabled: boolean) =>
    ipcRenderer.invoke("app:launch-at-login", enabled) as Promise<void>,
  login: () => ipcRenderer.invoke("auth:login") as Promise<{ started: boolean; message?: string }>,
  importAuth: () => ipcRenderer.invoke("auth:import") as Promise<{ connected: boolean }>,
  logout: () => ipcRenderer.invoke("auth:logout") as Promise<void>,
  showWindow: () => ipcRenderer.invoke("app:show") as Promise<void>,
  quit: () => ipcRenderer.invoke("app:quit") as Promise<void>,
  onBackendEvent: (listener: (event: BackendEvent) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: BackendEvent) => listener(payload);
    ipcRenderer.on("backend:event", handler);
    return () => ipcRenderer.removeListener("backend:event", handler);
  }
};

contextBridge.exposeInMainWorld("syncrotify", api);
