/* Bounded, read-only previews using the real renderer and current local edits.
 * No screenshot service, duplicate layout implementation, or eager deck fetch. */
(function () {
  'use strict';
  window.SlidePreviews = function (root, payloadFor) {
    var records = new Map(), enabled = false, active = null;
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var record = records.get(entry.target);
        if (!record) return;
        record.visible = entry.isIntersecting;
        if (!record.visible) retire(record);
      });
      pump();
    }, {root:root, rootMargin:'80px 0px'});
    var resize = new ResizeObserver(function(entries) {
      entries.forEach(function(entry) {scale(records.get(entry.target));});
    });
    function scale(record) {
      if (record && record.frame) record.frame.style.transform = 'scale(' + record.art.clientWidth / 1920 + ')';
    }
    function retire(record) {
      clearTimeout(record.timer);
      if (record.frame) record.frame.remove();
      record.frame = null;
      record.art.classList.remove('preview-ready');
      if (active === record) active = null;
    }
    function pump() {
      if (!enabled || active || document.hidden) return;
      var record = Array.from(records.values()).find(function(r) {return r.visible && !r.frame && !r.failed;});
      if (!record) return;
      active = record;
      var frame = document.createElement('iframe');
      record.frame = frame;
      frame.className = 'slide-preview'; frame.tabIndex = -1;
      frame.setAttribute('aria-hidden', 'true'); frame.title = 'Slide preview';
      frame.src = '?preview=1&v=' + window.slidekitAssetRevision + '#' + encodeURIComponent(record.id);
      record.art.appendChild(frame); scale(record);
      record.timer = setTimeout(function() {
        record.failed = true; retire(record); pump();
      }, 20000);
    }
    window.addEventListener('message', function(event) {
      if (event.origin !== location.origin || !event.data) return;
      var record = Array.from(records.values()).find(function(r) {return r.frame && r.frame.contentWindow === event.source;});
      if (!record) return;
      if (event.data.type === 'slidekit-preview-request') {
        payloadFor(record.id).then(function(payload) {
          if (record.frame && record.frame.contentWindow === event.source)
            event.source.postMessage({type:'slidekit-preview-data',payload:payload}, location.origin);
        }).catch(function() {record.failed = true; retire(record); pump();});
      } else if (event.data.type === 'slidekit-preview-ready') {
        clearTimeout(record.timer);
        record.art.classList.add('preview-ready');
        if (active === record) active = null;
        pump();
      }
    });
    document.addEventListener('visibilitychange', pump);
    this.sync = function () {
      records.forEach(function(record, art) {
        if (!art.isConnected) {retire(record); observer.unobserve(art); resize.unobserve(art); records.delete(art);}
      });
      root.querySelectorAll('.thumb-art').forEach(function(art) {
        if (records.has(art)) return;
        records.set(art, {art:art,id:art.closest('[data-id]').dataset.id,visible:false,frame:null});
        observer.observe(art); resize.observe(art);
      });
      pump();
    };
    this.start = function () {enabled = true; pump();};
    this.pause = function () {enabled = false;};
  };
}());
