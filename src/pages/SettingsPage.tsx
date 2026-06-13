import { useEffect, useState, type ReactNode } from "react";
import type { AppConfig } from "../types";
import { Button, Switch } from "../components/Controls";

type SettingsTab = "sync" | "download" | "metadata" | "system";

interface SettingsPageProps {
  config: AppConfig;
  onSave: (config: AppConfig) => void;
}

export function SettingsPage({ config, onSave }: SettingsPageProps) {
  const [draft, setDraft] = useState(() => structuredClone(config));
  const [tab, setTab] = useState<SettingsTab>("download");

  useEffect(() => setDraft(structuredClone(config)), [config]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(config);

  return (
    <div className="page settings-page">
      <header className="settings-header">
        <h1>Settings</h1>
        <p>Configure synchronization, downloads, metadata, and app behavior.</p>
      </header>
      <div className="settings-tabs" role="tablist">
        {(["sync", "download", "metadata", "system"] as const).map((id) => (
          <button
            aria-selected={tab === id}
            className={tab === id ? "selected" : ""}
            key={id}
            onClick={() => setTab(id)}
            role="tab"
            type="button"
          >
            {id[0].toUpperCase() + id.slice(1)}
          </button>
        ))}
      </div>
      <div className="settings-body">
        <div className="settings-form">
          {tab === "download" ? (
            <DownloadSettings draft={draft} setDraft={setDraft} />
          ) : null}
          {tab === "sync" ? <SyncSettings draft={draft} setDraft={setDraft} /> : null}
          {tab === "metadata" ? (
            <MetadataSettings draft={draft} setDraft={setDraft} />
          ) : null}
          {tab === "system" ? (
            <SystemSettings draft={draft} setDraft={setDraft} />
          ) : null}
        </div>
        <aside className="example-output">
          <span>Example output</span>
          <strong>
            {draft.filenameTemplate
              .replace("{artist}", "The Paper Kites")
              .replace("{title}", "Bloom")
              .replace("{album}", "Woodland")
              .replace("{year}", "2010")
              .replace("{track}", "01")}
            .{draft.audioFormat}
          </strong>
          <small>{draft.destinations[draft.activeMode].path || "No destination selected"}</small>
        </aside>
      </div>
      <footer className="settings-actions">
        <Button onClick={() => setDraft(structuredClone(config))}>Discard changes</Button>
        <span className={dirty ? "unsaved visible" : "unsaved"}>
          <i /> Changes have not been saved
        </span>
        <Button disabled={!dirty} onClick={() => onSave(draft)} variant="primary">
          Save changes
        </Button>
      </footer>
    </div>
  );
}

function DownloadSettings({
  draft,
  setDraft
}: {
  draft: AppConfig;
  setDraft: (config: AppConfig) => void;
}) {
  return (
    <>
      <Field label="Audio format">
        <select
          onChange={(event) =>
            setDraft({ ...draft, audioFormat: event.target.value as AppConfig["audioFormat"] })
          }
          value={draft.audioFormat}
        >
          <option value="m4a">M4A</option>
          <option value="mp3">MP3</option>
          <option value="opus">Opus</option>
          <option value="flac">FLAC</option>
        </select>
      </Field>
      <Field label="Audio quality">
        <select
          onChange={(event) =>
            setDraft({
              ...draft,
              audioQuality: event.target.value as AppConfig["audioQuality"]
            })
          }
          value={draft.audioQuality}
        >
          <option value="best">Best available</option>
          <option value="256k">256 kbps</option>
          <option value="128k">128 kbps</option>
          <option value="low">Low</option>
        </select>
      </Field>
      <Field
        helper="Available: {artist}, {title}, {album}, {year}, {track}"
        label="Filename template"
      >
        <input
          onChange={(event) => setDraft({ ...draft, filenameTemplate: event.target.value })}
          value={draft.filenameTemplate}
        />
      </Field>
      <Field label="File collision">
        <select
          onChange={(event) =>
            setDraft({
              ...draft,
              collisionStrategy: event.target.value as AppConfig["collisionStrategy"]
            })
          }
          value={draft.collisionStrategy}
        >
          <option value="smart_numbering">Smart numbering</option>
          <option value="skip">Skip</option>
          <option value="overwrite">Overwrite</option>
        </select>
      </Field>
      <Field label="Check file size before creating a duplicate">
        <Switch
          checked={draft.sizeCheckEnabled}
          label=""
          onChange={(checked) => setDraft({ ...draft, sizeCheckEnabled: checked })}
        />
      </Field>
      <Field label="Maximum duplicates">
        <input
          min={1}
          onChange={(event) =>
            setDraft({ ...draft, maxDuplicates: Number(event.target.value) })
          }
          type="number"
          value={draft.maxDuplicates}
        />
      </Field>
      <Field label="Path truncate length">
        <div className="range-control">
          <input
            max={200}
            min={20}
            onChange={(event) =>
              setDraft({ ...draft, pathTruncateLength: Number(event.target.value) })
            }
            type="range"
            value={draft.pathTruncateLength}
          />
          <span>{draft.pathTruncateLength} characters</span>
        </div>
      </Field>
    </>
  );
}

function SyncSettings({
  draft,
  setDraft
}: {
  draft: AppConfig;
  setDraft: (config: AppConfig) => void;
}) {
  return (
    <>
      <Field label="Playlist URL">
        <input
          onChange={(event) => setDraft({ ...draft, playlistUrl: event.target.value })}
          value={draft.playlistUrl}
        />
      </Field>
      <Field label="Automatic sync interval">
        <input
          min={30}
          onChange={(event) => setDraft({ ...draft, interval: Number(event.target.value) })}
          type="number"
          value={draft.interval}
        />
      </Field>
      <Field label="Smart stop threshold">
        <input
          min={1}
          onChange={(event) =>
            setDraft({ ...draft, smartStopThreshold: Number(event.target.value) })
          }
          type="number"
          value={draft.smartStopThreshold}
        />
      </Field>
      <Field label="Sync policy">
        <select
          onChange={(event) =>
            setDraft({
              ...draft,
              syncPolicy: event.target.value as AppConfig["syncPolicy"]
            })
          }
          value={draft.syncPolicy}
        >
          <option value="mirror">Exact mirror</option>
          <option value="additive">Add/update only</option>
        </select>
      </Field>
    </>
  );
}

function MetadataSettings({
  draft,
  setDraft
}: {
  draft: AppConfig;
  setDraft: (config: AppConfig) => void;
}) {
  return (
    <>
      <Field label="Cover format">
        <select
          onChange={(event) =>
            setDraft({
              ...draft,
              coverFormat: event.target.value as AppConfig["coverFormat"]
            })
          }
          value={draft.coverFormat}
        >
          <option value="JPEG">JPEG</option>
          <option value="PNG">PNG</option>
        </select>
      </Field>
      <Field label="Cover width">
        <input
          onChange={(event) =>
            setDraft({ ...draft, coverWidth: Number(event.target.value) })
          }
          type="number"
          value={draft.coverWidth}
        />
      </Field>
      <Field label="Cover height">
        <input
          onChange={(event) =>
            setDraft({ ...draft, coverHeight: Number(event.target.value) })
          }
          type="number"
          value={draft.coverHeight}
        />
      </Field>
      <Field label="Embed lyrics">
        <Switch
          checked={draft.embedLyrics}
          label=""
          onChange={(checked) => setDraft({ ...draft, embedLyrics: checked })}
        />
      </Field>
    </>
  );
}

function SystemSettings({
  draft,
  setDraft
}: {
  draft: AppConfig;
  setDraft: (config: AppConfig) => void;
}) {
  return (
    <>
      <Field label="Launch at login">
        <Switch
          checked={draft.launchAtLogin}
          label=""
          onChange={(checked) => setDraft({ ...draft, launchAtLogin: checked })}
        />
      </Field>
      <Field label="When the window closes">
        <select
          onChange={(event) =>
            setDraft({
              ...draft,
              closeBehavior: event.target.value as AppConfig["closeBehavior"]
            })
          }
          value={draft.closeBehavior}
        >
          <option value="tray">Keep running in tray</option>
          <option value="quit">Quit Syncrotify</option>
        </select>
      </Field>
    </>
  );
}

function Field({
  label,
  helper,
  children
}: {
  label: string;
  helper?: string;
  children: ReactNode;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <div>
        {children}
        {helper ? <small>{helper}</small> : null}
      </div>
    </label>
  );
}
