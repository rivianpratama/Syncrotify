export type DestinationMode = "folder" | "rockbox" | "ipod";
export type SyncPolicy = "mirror" | "additive";
export type CloseBehavior = "tray" | "quit";
export type SyncStatus =
  | "idle"
  | "waiting"
  | "planning"
  | "approval"
  | "syncing"
  | "completed"
  | "cancelled"
  | "failed";

export interface DestinationConfig {
  path: string;
  deviceId: string | null;
  displayName: string;
  approved: boolean;
  autoSync: boolean;
}

export interface AppConfig {
  playlistUrl: string;
  playlistName: string;
  activeMode: DestinationMode;
  syncPolicy: SyncPolicy;
  closeBehavior: CloseBehavior;
  launchAtLogin: boolean;
  interval: number;
  smartStopThreshold: number;
  skipDurationThreshold: number;
  maxRetries: number;
  audioFormat: "m4a" | "mp3" | "opus" | "flac";
  audioQuality: "best" | "256k" | "128k" | "low";
  filenameTemplate: string;
  collisionStrategy: "smart_numbering" | "skip" | "overwrite";
  sizeCheckEnabled: boolean;
  maxDuplicates: number;
  pathTruncateLength: number;
  coverFormat: "JPEG" | "PNG";
  coverWidth: number;
  coverHeight: number;
  coverQuality: number;
  embedLyrics: boolean;
  stagingCacheEnabled: boolean;
  destinations: Record<DestinationMode, DestinationConfig>;
}

export interface DeviceInfo {
  id: string;
  mode: Exclude<DestinationMode, "folder">;
  name: string;
  model: string;
  path: string;
  connected: boolean;
  experimental: boolean;
  freeBytes: number;
  totalBytes: number;
}

export interface SyncPlan {
  add: number;
  update: number;
  remove: number;
  requiresApproval: boolean;
  backupRequired: boolean;
}

export interface SyncProgress {
  status: SyncStatus;
  phase: string;
  message: string;
  current: number;
  total: number;
  percent: number;
  trackTitle?: string;
  trackArtist?: string;
  plan?: SyncPlan;
}

export interface ActivityEvent {
  id: string;
  timestamp: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
}

export interface BootstrapState {
  config: AppConfig;
  devices: DeviceInfo[];
  authConnected: boolean;
  progress: SyncProgress;
  activity: ActivityEvent[];
  nextAutoSyncAt: number | null;
  platform: string;
  version: string;
}

export type BackendEvent =
  | { type: "progress"; payload: SyncProgress }
  | { type: "activity"; payload: ActivityEvent }
  | { type: "devices"; payload: DeviceInfo[] }
  | { type: "config"; payload: AppConfig }
  | { type: "scheduler"; payload: { nextAutoSyncAt: number | null } }
  | { type: "auth"; payload: { connected: boolean } };

export interface SyncrotifyApi {
  bootstrap(): Promise<BootstrapState>;
  saveConfig(config: AppConfig): Promise<AppConfig>;
  chooseDirectory(): Promise<string | null>;
  startSync(): Promise<{ accepted: boolean }>;
  stopSync(): Promise<void>;
  approveSync(): Promise<void>;
  refreshDevices(): Promise<DeviceInfo[]>;
  ejectDevice(deviceId: string): Promise<void>;
  setLaunchAtLogin(enabled: boolean): Promise<void>;
  login(): Promise<{ started: boolean; message?: string }>;
  importAuth(): Promise<{ connected: boolean }>;
  logout(): Promise<void>;
  showWindow(): Promise<void>;
  quit(): Promise<void>;
  onBackendEvent(listener: (event: BackendEvent) => void): () => void;
}
