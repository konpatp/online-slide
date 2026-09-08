/* Layout picker. Previews use the real slide renderer; creation is idempotent. */
(function () {
  'use strict';
  window.SlideCreator = function (options) {
    const dialog = document.querySelector('[data-create-dialog]');
    const open = document.querySelector('[data-new-slide]');
    const list = dialog.querySelector('[data-layout-list]');
    const preview = dialog.querySelector('[data-layout-preview]');
    const detail = dialog.querySelector('[data-layout-description]');
    const message = dialog.querySelector('[data-create-message]');
    const add = dialog.querySelector('[data-create-confirm]');
    const storageKey = 'slidekit-create:' + location.pathname;
    let layouts, layoutsPromise, chosen, frame, posting = false, intent = null;
    let booted = false, requested = false, previewTimer, readyRevision = null, warmStarted = false;
    const loading = document.createElement('button');
    loading.type = 'button'; loading.className = 'layout-preview-loading';
    loading.addEventListener('click', () => {if (chosen) {retireFrame(); showPreview();}});
    try { intent = JSON.parse(localStorage.getItem(storageKey)); } catch (_) {}

    this.refresh = function () {
      open.disabled = !options.ready() || posting;
      add.disabled = !options.ready() || posting || !chosen;
    };
    const refresh = this.refresh;

    function payload() {
      return {schema: 'online-slide/state@4', revision: 0, order: ['layout-preview'], hidden: [],
        overlays: {}, tables: {}, objects: {}, sourceRevision: chosen.id,
        runtimeRevision: window.slidekitAssetRevision,
        slideRevisions: {'layout-preview': chosen.id}, slides: {'layout-preview': chosen.slide},
        loadedSlides: ['layout-preview']};
    }
    function retireFrame() {
      clearTimeout(previewTimer); if(frame) frame.remove(); frame = null;
      booted = false; requested = false; readyRevision = null;
    }
    function showPreview() {
      if (!chosen) return;
      if (readyRevision === chosen.id && frame) {loading.remove(); return;}
      loading.textContent = 'Loading preview…'; loading.disabled = true;
      preview.appendChild(loading); preview.setAttribute('aria-busy', 'true');
      clearTimeout(previewTimer);
      previewTimer = setTimeout(() => {
        loading.textContent = 'Preview unavailable · click to retry'; loading.disabled = false;
        preview.setAttribute('aria-busy', 'false');
      }, 10000);
      if (!frame) {
        frame = document.createElement('iframe'); frame.tabIndex = -1;
        frame.src = './?preview=1&v=' + window.slidekitAssetRevision + '#layout-preview';
        preview.appendChild(frame);
      }
      frame.title = chosen.name + ' layout preview';
      if (booted || requested) frame.contentWindow.postMessage({
        type: booted ? 'slidekit-preview-update' : 'slidekit-preview-data', payload: payload()
      }, location.origin);
    }

    function select(id) {
      const next = layouts.find(item => item.id === id) || layouts[0];
      if (chosen?.id !== next.id) readyRevision = null;
      chosen = next;
      list.querySelectorAll('button').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.layout === chosen.id));
        button.disabled = Boolean(intent) && button.dataset.layout !== intent.template;
      });
      detail.textContent = chosen.description;
      showPreview();
      add.textContent = intent ? 'Retry creating slide' : 'Create slide';
      refresh();
    }

    // The iframe asks for one immutable template, never live editing state.
    addEventListener('message', function (event) {
      if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
      if (event.data?.type === 'slidekit-preview-request') {requested = true; showPreview();}
      if (event.data?.type === 'slidekit-preview-initialized') {
        booted = true;
        if (event.data.revision !== chosen.id) showPreview();
      }
      if (event.data?.type === 'slidekit-preview-ready') {
        booted = true;
        if (event.data.revision !== chosen.id) {showPreview(); return;}
        readyRevision = chosen.id; clearTimeout(previewTimer); loading.remove();
        preview.setAttribute('aria-busy', 'false');
      }
    });

    function loadLayouts() {
      if (!layoutsPromise) layoutsPromise = window.slidekitRequest('api/layouts').then(response => {
        if (!response.ok) throw new Error('Could not load layouts. Close and try again.');
        return response.json();
      }).then(items => {
        layouts = items; list.replaceChildren();
        layouts.forEach(item => {
          const button = document.createElement('button');
          button.type = 'button'; button.dataset.layout = item.id; button.textContent = item.name;
          button.addEventListener('click', () => select(item.id)); list.appendChild(button);
        });
      }).catch(error => {layoutsPromise = null; throw error;});
      return layoutsPromise;
    }
    this.warm = function () {
      if (warmStarted) return;
      warmStarted = true;
      // Only after the main slide's first useful paint. One bounded host is
      // retained for this document; never pre-render six independent engines.
      loadLayouts().then(() => {if (!chosen) select(intent?.template || 'section-divider');}).catch(() => {});
    };

    this.show = async function (preferred) {
      if (!options.ready()) return;
      dialog.showModal();
      message.textContent = intent ? 'A previous creation has an uncertain response. Retry safely—no duplicate slide will be added.' :
        'Inserted after the current slide. Edit the placeholders, then reorder or hide it in the sidebar.';
      try {
        await loadLayouts();
        if (dialog.open) select(intent?.template || preferred || 'section-divider');
      } catch (error) { message.textContent = error.message; }
    };
    open.addEventListener('click', () => this.show());
    addEventListener('pagehide', retireFrame, {once:true});
    dialog.addEventListener('cancel', event => { if (posting) event.preventDefault(); });
    dialog.querySelector('[data-create-cancel]').addEventListener('click', () => { if (!posting) dialog.close(); });
    add.addEventListener('click', async () => {
      if (posting || !chosen || !options.ready()) return;
      posting = true; refresh();
      dialog.querySelector('[data-create-cancel]').disabled = true;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        intent ||= {requestId: crypto.randomUUID(), template: chosen.id, after: options.currentId()};
        // Retain before sending: even a reload after a lost ACK can retry once.
        localStorage.setItem(storageKey, JSON.stringify(intent));
        message.textContent = 'Creating and saving…';
        const response = await window.slidekitRequest('api/slides', {method: 'POST', signal: controller.signal,
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify(intent)});
        const payload = await response.json();
        if (!response.ok) {
          if (response.status === 400 || response.status === 409) {
            localStorage.removeItem(storageKey); intent = null;
          }
          throw new Error(payload.error || 'Could not create the slide');
        }
        localStorage.removeItem(storageKey); intent = null;
        dialog.close(); options.created(payload);
      } catch (error) {
        message.textContent = intent ? 'No confirmed response. Retry safely with the same request. ' +
          (error.name === 'AbortError' ? 'The server took too long to respond.' : error.message) : error.message;
        select(chosen.id);
      } finally {
        clearTimeout(timeout); posting = false;
        dialog.querySelector('[data-create-cancel]').disabled = false; refresh();
      }
    });
    refresh();
  };
}());
