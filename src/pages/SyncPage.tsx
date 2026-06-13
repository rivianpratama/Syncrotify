import { useEffect, useState } from "react";
import {
  Check,
  CircleStop,
  Database,
  Folder,
  HardDrive,
  Library,
  Music2,
  Minus,
  Play,
  Plus,
  RefreshCw,
  Scale,
  Settings,
  ShieldCheck,
  Smartphone,
  Unplug
} from "lucide-react";
import type {
  AppConfig,
  DestinationMode,
  DeviceInfo,
  SyncProgress
} from "../types";
import { Button, ProgressBar, Switch } from "../components/Controls";

const modes: Array<{
  id: DestinationMode;
  label: string;
  icon: typeof Folder;
}> = [
  { id: "folder", label: "Folder", icon: Folder },
  { id: "rockbox", label: "MP3 Player", icon: HardDrive },
  { id: "ipod", label: "iPod", icon: Smartphone }
];

interface SyncPageProps {
  config: AppConfig;
  progress: SyncProgress;
  device: DeviceInfo | null;
  authConnected: boolean;
  onModeChange: (mode: DestinationMode) => void;
  onChooseDestination: () => void;
  onConfigChange: (config: AppConfig) => void;
  onStart: () => void;
  onStop: () => void;
  onApprove: () => void;
  onEject: () => void;
  onLogin: () => void;
  onLogout: () => void;
  nextAutoSyncAt: number | null;
}

export function formatBytes(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function formatCountdown(nextRunAt: number, now: number): string {
  const remaining = Math.max(0, Math.ceil(nextRunAt - now));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

function disconnectedTitle(config: AppConfig): string {
  const destination = config.destinations[config.activeMode];
  if (destination.deviceId) {
    return `${destination.displayName} is disconnected`;
  }
  return config.activeMode === "ipod"
    ? "No iPod connected"
    : "No MP3 player connected";
}

export function SyncPage({
  config,
  progress,
  device,
  authConnected,
  onModeChange,
  onChooseDestination,
  onConfigChange,
  onStart,
  onStop,
  onApprove,
  onEject,
  onLogin,
  onLogout,
  nextAutoSyncAt
}: SyncPageProps) {
  const [editingPlaylist, setEditingPlaylist] = useState(false);
  const [playlistUrl, setPlaylistUrl] = useState(config.playlistUrl);
  const [now, setNow] = useState(Date.now() / 1000);
  const busy =
    progress.status === "syncing" ||
    progress.status === "planning" ||
    progress.status === "approval";
  const destination = config.destinations[config.activeMode];
  const isFolder = config.activeMode === "folder";
  const canSync =
    authConnected &&
    Boolean(config.playlistUrl.trim()) &&
    Boolean(destination.path) &&
    (isFolder || Boolean(device));
  const freePercent =
    device && device.totalBytes > 0
      ? ((device.totalBytes - device.freeBytes) / device.totalBytes) * 100
      : 0;

  useEffect(() => setPlaylistUrl(config.playlistUrl), [config.playlistUrl]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const setAutoSync = (checked: boolean) => {
    const next = structuredClone(config);
    next.destinations[next.activeMode].autoSync = checked;
    onConfigChange(next);
  };

  const setStagingCache = (enabled: boolean) => {
    onConfigChange({ ...config, stagingCacheEnabled: enabled });
  };

  const savePlaylist = () => {
    onConfigChange({
      ...config,
      playlistUrl: playlistUrl.trim(),
      playlistName: ""
    });
    setEditingPlaylist(false);
  };

  const schedulerText = isFolder
    ? !destination.autoSync
      ? "Automatic sync is off"
      : !config.playlistUrl
        ? "Add a playlist URL to schedule automatic sync"
        : nextAutoSyncAt
          ? `Next automatic sync in ${formatCountdown(nextAutoSyncAt, now)}`
          : "Automatic sync will be scheduled after configuration is saved"
    : !destination.autoSync
      ? "Connect-triggered sync is off"
      : destination.deviceId
        ? "Sync starts when this paired device connects"
        : "Pair a device to enable connect-triggered sync";

  return (
    <div className="page sync-page">
      <header className="page-header">
        <div>
          <h1>Library sync</h1>
        </div>
        <div className="auth-status">
          <span className={`status-dot ${authConnected ? "connected" : ""}`}>
            {authConnected ? <Check /> : null}
          </span>
          <span>{authConnected ? "YouTube Music connected" : "Not connected"}</span>
          <button onClick={authConnected ? onLogout : onLogin} type="button">
            {authConnected ? "Sign out" : "Connect"}
          </button>
        </div>
      </header>

      <section>
        <div className="section-label">DESTINATION MODE</div>
        <div className="mode-selector" role="tablist">
          {modes.map(({ id, label, icon: Icon }) => (
            <button
              aria-selected={config.activeMode === id}
              className={config.activeMode === id ? "selected" : ""}
              disabled={busy}
              key={id}
              onClick={() => onModeChange(id)}
              role="tab"
              type="button"
            >
              <Icon />
              <span>{label}</span>
              {config.activeMode === id ? <Check className="selected-check" /> : null}
            </button>
          ))}
        </div>
      </section>

      <section className="device-band">
        <div className="device-icon">
          {config.activeMode === "folder" ? <Folder /> : <Smartphone />}
        </div>
        <div className="device-name">
          <strong>
            {isFolder
              ? destination.displayName || "Music folder"
              : device?.name ?? disconnectedTitle(config)}
          </strong>
          <span>
            {isFolder
              ? destination.path || "No folder selected"
              : device?.model ??
                (destination.deviceId
                  ? "The paired device is not currently connected"
                  : "Connect and select a device to pair it")}
          </span>
        </div>
        <div className="device-capacity">
          {isFolder ? (
            <>
              <span className={destination.path ? "connected-text" : "muted"}>
                {destination.path ? <i /> : null}
                {destination.path ? "Ready" : "Not configured"}
              </span>
              <span>Local folder destination; no device is required</span>
            </>
          ) : device ? (
            <>
              <span className="connected-text">
                <i /> Connected
              </span>
              <span>
                {formatBytes(device.freeBytes)} free of {formatBytes(device.totalBytes)}
              </span>
              <ProgressBar value={freePercent} tone="success" />
            </>
          ) : (
            <span className="muted">Disconnected</span>
          )}
        </div>
        <div className="device-actions">
          {config.activeMode !== "folder" ? (
            <Button disabled={!device} icon={<Unplug />} onClick={onEject}>
              Eject
            </Button>
          ) : null}
          <Button icon={<Settings />} onClick={onChooseDestination}>
            {isFolder
              ? "Change folder"
              : config.activeMode === "rockbox"
                ? "Choose MP3 player folder"
                : "Choose iPod folder"}
          </Button>
          {config.activeMode === "ipod" ? (
            <span className="experimental">Experimental stock iPod support</span>
          ) : null}
        </div>
      </section>

      <section className="config-band">
        <div className="config-row">
          <span className="config-icon">
            <Music2 />
          </span>
          <span className="config-label">PLAYLIST SOURCE</span>
          <span className="config-value">
            {editingPlaylist ? (
              <input
                autoFocus
                className="inline-config-input"
                onChange={(event) => setPlaylistUrl(event.target.value)}
                placeholder="https://music.youtube.com/playlist?list=..."
                type="url"
                value={playlistUrl}
              />
            ) : (
              <>
                <strong>{config.playlistName || "YouTube Music playlist"}</strong>
                <small>{config.playlistUrl || "No playlist selected"}</small>
              </>
            )}
          </span>
          {editingPlaylist ? (
            <div className="inline-config-actions">
              <Button onClick={() => setEditingPlaylist(false)}>Cancel</Button>
              <Button onClick={savePlaylist} variant="primary">Save</Button>
            </div>
          ) : (
            <Button disabled={busy} onClick={() => setEditingPlaylist(true)}>Change</Button>
          )}
        </div>
        <div className="config-row">
          <span className="config-icon">
            <Scale />
          </span>
          <span className="config-label">SYNC POLICY</span>
          <span className="config-value">
            <strong>{config.syncPolicy === "mirror" ? "Exact mirror" : "Add/update only"}</strong>
            <small>
              {config.syncPolicy === "mirror"
                ? "Add, update, and remove Syncrotify-managed tracks"
                : "Never remove tracks automatically"}
            </small>
          </span>
          <Button
            disabled={busy}
            onClick={() =>
              onConfigChange({
                ...config,
                syncPolicy: config.syncPolicy === "mirror" ? "additive" : "mirror"
              })
            }
          >
            Change
          </Button>
        </div>
        <div className="config-row">
          <span className="config-icon">
            <Database />
          </span>
          <span className="config-label">STAGING CACHE</span>
          <span className="config-value">
            <strong>
              {isFolder
                ? "Not used"
                : config.stagingCacheEnabled
                  ? "Enabled"
                  : "Disabled"}
            </strong>
            <small>
              {isFolder
                ? "Files are written directly to the selected folder"
                : config.stagingCacheEnabled
                  ? "Downloaded files are retained locally after transfer"
                  : "Temporary downloaded files are removed after transfer"}
            </small>
          </span>
          {!isFolder ? (
            <Button
              disabled={busy}
              onClick={() => setStagingCache(!config.stagingCacheEnabled)}
            >
              {config.stagingCacheEnabled ? "Disable" : "Enable"}
            </Button>
          ) : null}
        </div>
      </section>

      <div className="primary-actions">
        {progress.status === "approval" ? (
          <Button icon={<ShieldCheck />} onClick={onApprove} variant="primary">
            Approve first sync
          </Button>
        ) : (
          <Button disabled={busy || !canSync} icon={<Play />} onClick={onStart} variant="primary">
            Sync now
          </Button>
        )}
        <Button
          disabled={!busy}
          icon={<CircleStop />}
          onClick={onStop}
        >
          Stop sync
        </Button>
        {!canSync && !busy ? (
          <span className="sync-readiness">
            {!authConnected
              ? "Connect YouTube Music before syncing."
              : !config.playlistUrl
                ? "Add a playlist URL before syncing."
                : !destination.path
                  ? "Choose a destination before syncing."
                  : !isFolder && !device
                    ? "Connect the selected device before syncing."
                    : ""}
          </span>
        ) : null}
      </div>

      <div className="sync-grid">
        <section className="panel current-sync">
          <h2>Current sync</h2>
          {progress.status === "idle" ? (
            <div className="panel-empty">
              <Library />
              <strong>No sync has run</strong>
              <span>Configure a playlist and destination, then start a sync.</span>
            </div>
          ) : !busy ? (
            <div className={`sync-result ${progress.status}`}>
              <strong>{progress.phase}</strong>
              <span>{progress.message}</span>
            </div>
          ) : (
            <ol className="sync-steps">
            <SyncStep complete={progress.percent > 5} index={1} label="Checking playlist" />
            <SyncStep complete={progress.percent > 20} index={2} label="Preparing tracks" />
            <li className="active-step">
              <span className="step-index">
                <Library />
              </span>
              <div className="active-step-content">
                <div>
                  <strong>{progress.phase || "Waiting to sync"}</strong>
                  <span>{progress.percent}%</span>
                </div>
                <ProgressBar value={progress.percent} />
                <div className="track-progress">
                  {progress.trackTitle ? <Music2 /> : null}
                  <span>{progress.trackTitle ?? ""}</span>
                  <span>{progress.trackArtist ?? ""}</span>
                  <span>{progress.message}</span>
                </div>
              </div>
            </li>
            <SyncStep
              complete={progress.percent >= 88}
              index={4}
              label={
                config.activeMode === "ipod"
                  ? "Updating iPod database"
                  : "Updating destination manifest"
              }
            />
            <SyncStep
              complete={progress.status === "completed"}
              index={5}
              label="Verifying and cleaning cache"
            />
            </ol>
          )}
        </section>

        <section className="panel sync-plan">
          <h2>Sync plan</h2>
          {progress.plan ? (
            <>
              <div className="plan-stat add">
                <span><Plus /></span>
                <strong>{progress.plan.add}</strong>
                <small>add</small>
              </div>
              <div className="plan-stat update">
                <span><RefreshCw /></span>
                <strong>{progress.plan.update}</strong>
                <small>update</small>
              </div>
              <div className="plan-stat remove">
                <span><Minus /></span>
                <strong>{progress.plan.remove}</strong>
                <small>remove</small>
              </div>
              {progress.plan.backupRequired ? (
                <div className="backup-note">
                  <ShieldCheck />
                  <span>Database backup required before changes</span>
                </div>
              ) : null}
            </>
          ) : (
            <div className="panel-empty compact">
              <Database />
              <strong>No plan calculated</strong>
              <span>A plan appears after the source playlist is checked.</span>
            </div>
          )}
        </section>
      </div>

      <footer className="sync-footer">
        <Switch
          checked={destination.autoSync}
          label={
            config.activeMode === "folder"
              ? "Run automatic sync on schedule"
              : "Auto sync when this device connects"
          }
          onChange={setAutoSync}
        />
        <span>{schedulerText}</span>
      </footer>
    </div>
  );
}

function SyncStep({
  index,
  label,
  complete
}: {
  index: number;
  label: string;
  complete: boolean;
}) {
  return (
    <li>
      <span className="step-index">{complete ? <Check /> : index}</span>
      <span>{label}</span>
      <span className={complete ? "complete" : "pending"}>
        {complete ? "Complete" : "Pending"}
      </span>
    </li>
  );
}
