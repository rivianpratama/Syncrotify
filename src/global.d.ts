import type { SyncrotifyApi } from "./types";

declare global {
  interface Window {
    syncrotify: SyncrotifyApi;
  }
}

export {};
