import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type {
  AppConfig,
  BootstrapState,
  DestinationMode,
  DeviceInfo
} from "./types";

export function useSyncrotify() {
  const [state, setState] = useState<BootstrapState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stateRef = useRef<BootstrapState | null>(null);
  const saveChain = useRef(Promise.resolve());

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    let active = true;
    void api
      .bootstrap()
      .then((bootstrap) => {
        if (active) {
          stateRef.current = bootstrap;
          setState(bootstrap);
        }
      })
      .catch((reason: Error) => setError(reason.message));

    const unsubscribe = api.onBackendEvent((event) => {
      setState((current) => {
        if (!current) {
          return current;
        }
        switch (event.type) {
          case "progress":
            return { ...current, progress: event.payload };
          case "activity":
            return {
              ...current,
              activity: [...current.activity, event.payload].slice(-200)
            };
          case "devices":
            return { ...current, devices: event.payload };
          case "config":
            return { ...current, config: event.payload };
          case "scheduler":
            return { ...current, nextAutoSyncAt: event.payload.nextAutoSyncAt };
          case "auth":
            return { ...current, authConnected: event.payload.connected };
        }
      });
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const saveConfig = useCallback(async (config: AppConfig) => {
    const current = stateRef.current;
    if (current) {
      const optimistic = { ...current, config };
      stateRef.current = optimistic;
      setState(optimistic);
    }

    try {
      let saved = config;
      saveChain.current = saveChain.current.catch(() => undefined).then(async () => {
        saved = await api.saveConfig(config);
      });
      await saveChain.current;
      setState((latest) => {
        if (!latest || latest.config !== config) {
          return latest;
        }
        const reconciled = { ...latest, config: saved };
        stateRef.current = reconciled;
        return reconciled;
      });
      return saved;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      setError(message);
      throw reason;
    }
  }, []);

  const updateConfig = useCallback(
    async (update: (config: AppConfig) => AppConfig) => {
      const current = stateRef.current;
      if (!current) {
        return;
      }
      await saveConfig(update(structuredClone(current.config)));
    },
    [saveConfig]
  );

  const selectMode = useCallback(
    (mode: DestinationMode) =>
      updateConfig((config) => ({ ...config, activeMode: mode })),
    [updateConfig]
  );

  const refreshDevices = useCallback(async () => {
    const devices = await api.refreshDevices();
    setState((current) => (current ? { ...current, devices } : current));
  }, []);

  const chooseDestination = useCallback(async (requestedMode?: DestinationMode) => {
    const current = stateRef.current;
    if (!current) {
      return;
    }
    const path = await api.chooseDirectory();
    if (!path) {
      return;
    }
    await updateConfig((config) => {
      const mode = requestedMode ?? config.activeMode;
      const matchingDevice = current.devices.find(
        (device) => device.mode === mode && device.path.toLowerCase() === path.toLowerCase()
      );
      config.destinations[mode] = {
        ...config.destinations[mode],
        path,
        deviceId: matchingDevice?.id ?? null,
        displayName:
          matchingDevice?.name ??
          (mode === "folder"
            ? path.split(/[\\/]/).filter(Boolean).at(-1) || "Music folder"
            : mode === "rockbox"
              ? "MP3 Player"
              : "iPod"),
        approved: false
      };
      return config;
    });
  }, [updateConfig]);

  const activeDevice: DeviceInfo | null = state
    ? state.devices.find(
        (device) =>
          device.mode === state.config.activeMode &&
          (device.id === state.config.destinations[state.config.activeMode].deviceId ||
            device.path === state.config.destinations[state.config.activeMode].path)
      ) ??
      state.devices.find((device) => device.mode === state.config.activeMode) ??
      null
    : null;

  return {
    state,
    error,
    setError,
    activeDevice,
    saveConfig,
    updateConfig,
    selectMode,
    refreshDevices,
    chooseDestination,
    api
  };
}
