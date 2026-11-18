import { reportViewProgress, startVideoView } from './api';
import { deviceId } from './device';

// Counts a view only after this many seconds of genuine playback, so a
// video that merely flicks past while swiping never registers.
export const VIEW_AFTER_SECONDS = 3;
// Watch time is sent in batches rather than every second.
export const REPORT_EVERY_SECONDS = 10;
// "Completed" = got through this much of the video.
export const COMPLETE_FRACTION = 0.9;

export { deviceId };

// One tracker per mounted video. tick() is called about once a second
// while the video is actually playing; flush() sends whatever is unsent.
// Every network call is best-effort — tracking must never break playback.
export interface ViewApi {
  start: (postId: string, viewerKey: string) => Promise<{ view_id: string | null }>;
  report: (viewId: string, seconds: number, completed: boolean) => Promise<unknown>;
}

const defaultApi: ViewApi = { start: startVideoView, report: reportViewProgress };

export class ViewTracker {
  private playedTotal = 0;
  private unreported = 0;
  private viewId: string | null = null;
  private starting = false;
  private completed = false;
  private completedSent = false;
  private declined = false;

  constructor(private postId: string, private api: ViewApi = defaultApi) {}

  tick(seconds: number, fractionWatched: number) {
    if (this.declined) return;
    this.playedTotal += seconds;
    if (this.viewId || this.starting) {
      this.unreported += seconds;
    }
    if (!this.viewId && !this.starting && this.playedTotal >= VIEW_AFTER_SECONDS) {
      this.starting = true;
      const carried = this.playedTotal;
      this.api.start(this.postId, deviceId())
        .then((res) => {
          this.viewId = res.view_id;
          if (!res.view_id) this.declined = true; // e.g. the poster's own post
          else this.unreported += carried;
        })
        .catch(() => {
          this.declined = true;
        })
        .finally(() => {
          this.starting = false;
        });
    }
    if (fractionWatched >= COMPLETE_FRACTION) this.completed = true;
    if (this.viewId && (this.unreported >= REPORT_EVERY_SECONDS || (this.completed && !this.completedSent))) {
      this.flush();
    }
  }

  flush() {
    if (!this.viewId) return;
    const sendCompleted = this.completed && !this.completedSent;
    if (this.unreported < 0.5 && !sendCompleted) return;
    const seconds = Math.round(this.unreported * 10) / 10;
    this.unreported = 0;
    if (sendCompleted) this.completedSent = true;
    this.api.report(this.viewId, seconds, sendCompleted).catch(() => {});
  }
}
