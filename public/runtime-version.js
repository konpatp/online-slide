/* Never combine a running renderer with another release's source or ACK. */
(function () {
  'use strict';
  let stale = false;
  window.slidekitRuntimeStale = () => stale;
  window.slidekitRequest = async function (url, options) {
    if (stale) throw new Error('Slide renderer updated. Reload to continue; local edits are retained.');
    const headers = new Headers(options?.headers);
    headers.set('X-Slidekit-Runtime', window.slidekitAssetRevision);
    const requestUrl = new URL(url, document.baseURI);
    // Immutable source-response caches must not carry an older runtime header
    // into a newly loaded renderer, even when scientific source is unchanged.
    requestUrl.searchParams.set('runtime', window.slidekitAssetRevision);
    const response = await fetch(requestUrl, {...options, headers});
    const revision = response.headers.get('X-Slidekit-Runtime');
    if (revision && revision !== window.slidekitAssetRevision) {
      stale = true;
      dispatchEvent(new Event('slidekit-runtime-changed'));
      throw new Error('Slide renderer updated. Reload to continue; local edits are retained.');
    }
    return response;
  };
}());
