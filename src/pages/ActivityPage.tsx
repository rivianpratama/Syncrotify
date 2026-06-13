import { CheckCircle2, CircleAlert, Info, TriangleAlert } from "lucide-react";
import type { ActivityEvent, SyncProgress } from "../types";
import { ProgressBar } from "../components/Controls";

const icons = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  error: CircleAlert
};

export function ActivityPage({
  activity,
  progress
}: {
  activity: ActivityEvent[];
  progress: SyncProgress;
}) {
  return (
    <div className="page list-page">
      <header className="page-header">
        <div>
          <h1>Activity</h1>
          <p>Structured sync history and backend diagnostics.</p>
        </div>
      </header>
      <section className="activity-summary panel">
        <div>
          <span>Current status</span>
          <strong>{progress.phase}</strong>
          <small>{progress.message}</small>
        </div>
        <div>
          <span>{progress.percent}%</span>
          <ProgressBar value={progress.percent} />
        </div>
      </section>
      <section className="activity-list panel">
        {activity
          .slice()
          .reverse()
          .map((event) => {
            const Icon = icons[event.level];
            return (
              <div className={`activity-row ${event.level}`} key={event.id}>
                <Icon />
                <time>{event.timestamp}</time>
                <span>{event.message}</span>
              </div>
            );
          })}
        {activity.length === 0 ? (
          <div className="empty-state">
            <Info />
            <strong>No activity yet</strong>
            <span>Sync events will appear here.</span>
          </div>
        ) : null}
      </section>
    </div>
  );
}
