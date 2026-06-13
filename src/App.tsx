import { useState } from "react";
import { AppShell, type Page } from "./components/AppShell";
import { ActivityPage } from "./pages/ActivityPage";
import { DevicesPage } from "./pages/DevicesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SyncPage } from "./pages/SyncPage";
import { useSyncrotify } from "./useSyncrotify";
import type { DeviceInfo } from "./types";

export default function App() {
  const [page, setPage] = useState<Page>("sync");
  const {
    state,
    error,
    activeDevice,
    selectMode,
    refreshDevices,
    chooseDestination,
    saveConfig,
    updateConfig,
    api
  } = useSyncrotify();

  if (!state) {
    return (
      <div className="boot-screen">
        <div className="boot-mark" />
        <strong>Starting Syncrotify</strong>
        <span>{error ?? "Connecting to the sync engine..."}</span>
      </div>
    );
  }

  const selectDevice = (device: DeviceInfo) => {
    void updateConfig((config) => {
      config.activeMode = device.mode;
      config.destinations[device.mode] = {
        ...config.destinations[device.mode],
        path: device.path,
        deviceId: device.id,
        displayName: device.name,
        approved: false
      };
      return config;
    });
    setPage("sync");
  };

  return (
    <AppShell onPageChange={setPage} page={page}>
      {error ? (
        <button className="error-banner" onClick={() => window.location.reload()} type="button">
          {error}
        </button>
      ) : null}
      {page === "sync" ? (
        <SyncPage
          authConnected={state.authConnected}
          config={state.config}
          device={activeDevice}
          onApprove={() => void api.approveSync()}
          onChooseDestination={() => void chooseDestination()}
          onConfigChange={(config) => void saveConfig(config)}
          onEject={() =>
            activeDevice ? void api.ejectDevice(activeDevice.id) : undefined
          }
          onLogin={() => void api.login()}
          onLogout={() => void api.logout()}
          onModeChange={(mode) => void selectMode(mode)}
          onStart={() => void api.startSync()}
          onStop={() => void api.stopSync()}
          nextAutoSyncAt={state.nextAutoSyncAt}
          progress={state.progress}
        />
      ) : null}
      {page === "devices" ? (
        <DevicesPage
          config={state.config}
          devices={state.devices}
          onBrowse={() => void chooseDestination("folder")}
          onRefresh={() => void refreshDevices()}
          onSelect={selectDevice}
        />
      ) : null}
      {page === "activity" ? (
        <ActivityPage activity={state.activity} progress={state.progress} />
      ) : null}
      {page === "settings" ? (
        <SettingsPage config={state.config} onSave={(config) => void saveConfig(config)} />
      ) : null}
    </AppShell>
  );
}
