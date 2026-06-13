import { Folder, HardDrive, RefreshCw, Smartphone } from "lucide-react";
import type { AppConfig, DeviceInfo } from "../types";
import { Button, ProgressBar } from "../components/Controls";

interface DevicesPageProps {
  config: AppConfig;
  devices: DeviceInfo[];
  onRefresh: () => void;
  onSelect: (device: DeviceInfo) => void;
  onBrowse: () => void;
}

export function DevicesPage({
  config,
  devices,
  onRefresh,
  onSelect,
  onBrowse
}: DevicesPageProps) {
  return (
    <div className="page list-page">
      <header className="page-header">
        <div>
          <h1>Devices</h1>
          <p>Pair removable destinations and control connect-triggered sync.</p>
        </div>
        <Button icon={<RefreshCw />} onClick={onRefresh}>
          Refresh
        </Button>
      </header>
      <section className="device-list panel">
        <button className="device-list-row" onClick={onBrowse} type="button">
          <span className="large-row-icon">
            <Folder />
          </span>
          <span>
            <strong>Folder destination</strong>
            <small>{config.destinations.folder.path || "Choose a local folder"}</small>
          </span>
          <span className="row-state">Always available</span>
        </button>
        {devices.map((device) => (
          <button
            className="device-list-row"
            key={device.id}
            onClick={() => onSelect(device)}
            type="button"
          >
            <span className="large-row-icon">
              {device.mode === "rockbox" ? <HardDrive /> : <Smartphone />}
            </span>
            <span>
              <strong>{device.name}</strong>
              <small>{device.model}</small>
            </span>
            <span className="capacity-cell">
              <span>{(device.freeBytes / 1024 ** 3).toFixed(1)} GB free</span>
              <ProgressBar
                tone="success"
                value={((device.totalBytes - device.freeBytes) / device.totalBytes) * 100}
              />
            </span>
            <span className="row-state connected-text">
              {device.experimental ? "Experimental" : "Connected"}
            </span>
          </button>
        ))}
        {devices.length === 0 ? (
          <div className="empty-state">
            <HardDrive />
            <strong>No removable devices detected</strong>
            <span>Connect an MP3 player or supported iPod volume, then refresh.</span>
          </div>
        ) : null}
      </section>
    </div>
  );
}
