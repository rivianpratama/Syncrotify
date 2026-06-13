import type { ReactNode } from "react";
import {
  Activity,
  CircleHelp,
  Disc3,
  LogOut,
  Moon,
  RefreshCw,
  Settings,
  Smartphone
} from "lucide-react";

export type Page = "sync" | "devices" | "activity" | "settings";

const nav = [
  { id: "sync" as const, label: "Sync", icon: RefreshCw },
  { id: "devices" as const, label: "Devices", icon: Smartphone },
  { id: "activity" as const, label: "Activity", icon: Activity },
  { id: "settings" as const, label: "Settings", icon: Settings }
];

interface AppShellProps {
  page: Page;
  onPageChange: (page: Page) => void;
  children: ReactNode;
}

export function AppShell({ page, onPageChange, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Disc3 aria-hidden="true" />
          <span>Syncrotify</span>
        </div>
        <nav aria-label="Primary navigation">
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item ${page === id ? "selected" : ""}`}
              key={id}
              onClick={() => onPageChange(id)}
              type="button"
            >
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-footer">
          <button aria-label="Help" className="icon-button" type="button">
            <CircleHelp />
          </button>
          <button aria-label="Sign out" className="icon-button" type="button">
            <LogOut />
          </button>
          <button aria-label="Theme" className="icon-button" type="button">
            <Moon />
          </button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
