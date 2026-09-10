import type { RevisionedSnapshot, Snapshot, SaveRequest } from './model';
import { carryForward, sameSnapshot, snapshot } from './snapshot';

export interface SaveResponse { ok: boolean; status: number; payload: unknown }
export interface SaveHost<S extends RevisionedSnapshot> {
  current(): S;
  accepted(): S;
  decode(payload: unknown): S;
  request(body: SaveRequest): Promise<SaveResponse>;
  stale(): boolean;
  acceptedResult(remote: S, current: S, clean: boolean): void;
  conflict(remote: S, message: string): void;
  invalid(message: string): void;
  retry(error?: unknown): void;
  runtimeChanged(error: unknown): void;
  schedule(callback: () => void): void;
}
import { saveRequest } from './snapshot';

/** One writer, latest pending intent. No DOM, timers, fetch or global state.
 * The host owns transport, draft retention and view updates; this owns queue
 * transitions, including edits made while a request is outstanding.
 */
export class SaveQueue<S extends RevisionedSnapshot> {
  pending: Snapshot | null = null;
  inFlight: Snapshot | null = null;
  constructor(private readonly host: SaveHost<S>) {}
  enqueue(): void {
    this.pending = snapshot(this.host.current());
    this.flush();
  }
  flush = (): void => {
    if (this.host.stale() || this.inFlight || !this.pending) return;
    const job = this.pending;
    this.pending = null;
    this.inFlight = job;
    this.host.request(saveRequest(this.host.accepted(), job)).then(result => {
      this.inFlight = null;
      if (!result.ok) {
        const payload = result.payload as {state?: unknown; error?: string} | null;
        const message = payload?.error || 'Could not save slide edits';
        if (result.status === 409 && payload?.state) {
          const remote = this.host.decode(payload.state);
          this.pending = null;
          this.host.conflict(remote, message);
        } else if (result.status === 400) {
          this.pending = null;
          this.host.invalid(message);
        } else this.retry(job);
        return;
      }
      const remote = this.host.decode(result.payload);
      const current = carryForward(job, this.host.current(), remote);
      const clean = sameSnapshot(current, remote);
      this.pending = clean ? null : snapshot(current);
      this.host.acceptedResult(remote, current, clean);
      if (!clean) this.flush();
    }).catch(error => {
      this.inFlight = null;
      this.pending = this.pending || job;
      if (this.host.stale()) this.host.runtimeChanged(error);
      else this.retry(job, error);
    });
  };
  private retry(job: Snapshot, error?: unknown): void {
    this.pending = this.pending || job;
    this.host.retry(error);
    this.host.schedule(this.flush);
  }
}
