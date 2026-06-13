import type { SyncrotifyApi } from "./types";

function missingBridge(): never {
  throw new Error(
    "The Syncrotify desktop bridge did not load. Restart the app or reinstall this build."
  );
}

const unavailableApi: SyncrotifyApi = {
  bootstrap: async () => missingBridge(),
  saveConfig: async () => missingBridge(),
  chooseDirectory: async () => missingBridge(),
  startSync: async () => missingBridge(),
  stopSync: async () => missingBridge(),
  approveSync: async () => missingBridge(),
  refreshDevices: async () => missingBridge(),
  ejectDevice: async () => missingBridge(),
  setLaunchAtLogin: async () => missingBridge(),
  login: async () => missingBridge(),
  importAuth: async () => missingBridge(),
  logout: async () => missingBridge(),
  showWindow: async () => missingBridge(),
  quit: async () => missingBridge(),
  onBackendEvent: () => () => undefined
};

export const api: SyncrotifyApi =
  typeof window !== "undefined" && window.syncrotify
    ? window.syncrotify
    : unavailableApi;
