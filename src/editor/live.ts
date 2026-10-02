/** Live deck updates by a small, immediate version check.
 *
 * While the tab is visible the editor asks every few seconds whether the deck
 * changed (an agent published slides, another editor saved). Each check is a
 * tiny request that answers at once, so the network stays idle between them
 * (page tooling that waits for an idle network keeps working). Checks pause
 * while hidden, run immediately when the tab returns, and back off while the
 * server is unreachable (for example during a publication restart). A renderer
 * change surfaces through the request layer's runtime check.
 */
export interface LiveVersion { revision: number; sourceRevision: string; runtimeRevision: string; token: string }
interface LiveHost {
  /** Our accepted version as `revision:sourceRevision`, or null before boot. */
  token(): string | null;
  request(url: string): Promise<Response>;
  changed(version: LiveVersion): Promise<void> | void;
  enabled(): boolean;
}
export const LIVE_INTERVAL_MS = 3000;

export function createLiveUpdates(host: LiveHost, interval = LIVE_INTERVAL_MS) {
  let timer: ReturnType<typeof setTimeout> | undefined, checking = false, failures = 0;

  function schedule(delay: number) {
    clearTimeout(timer);
    if (host.enabled() && !document.hidden) timer = setTimeout(check, delay);
  }
  async function check() {
    if (checking || !host.enabled() || document.hidden) return;
    const token = host.token();
    if (!token) { schedule(500); return; }
    checking = true;
    let delay = interval;
    try {
      const response = await host.request('api/changes');
      if (!response.ok) throw new Error('live update status ' + response.status);
      const version = await response.json() as LiveVersion;
      failures = 0;
      if (version.token !== host.token()) await host.changed(version);
    } catch {
      // Unreachable (restart, network): retry soon, then less often.
      failures++;
      delay = Math.min(30000, interval * 2 ** Math.min(failures - 1, 4));
    } finally {
      checking = false;
      schedule(delay);
    }
  }
  const now = () => { clearTimeout(timer); check(); };
  document.addEventListener('visibilitychange', () => { if (!document.hidden) now(); else clearTimeout(timer); });
  window.addEventListener('focus', now);
  window.addEventListener('online', () => { failures = 0; now(); });
  return {start: now};
}
