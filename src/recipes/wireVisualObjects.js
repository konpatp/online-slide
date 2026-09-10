// Recipe owns layout; injected editor capabilities own mutable state.
export function createWireVisualObjects(api) {
const global = window;
const {objectsForSlide,selectedObjectId,selectVisualObject,updateVisualObject} = api;
function wireVisualObjects(slide,records) {
  var objectState=api.objectsForSlide(slide);
  function rounded(value) { return Math.round(value * 10000) / 10000; }

  function rectGeometry(record) {
    var outer = record.article.getBoundingClientRect();
    var box = record.element.getBoundingClientRect();
    return {kind: record.kind,
      x: rounded((box.left - outer.left) / outer.width),
      y: rounded((box.top - outer.top) / outer.height),
      width: rounded(box.width / outer.width),
      height: rounded(box.height / outer.height)};
  }

  function lineGeometry(record) {
    var outer = record.article.getBoundingClientRect();
    var box = record.element.getBoundingClientRect();
    return {kind: record.kind,
      from: [rounded((box.left - outer.left) / outer.width),
        rounded((box.top + box.height / 2 - outer.top) / outer.height)],
      to: [rounded((box.right - outer.left) / outer.width),
        rounded((box.top + box.height / 2 - outer.top) / outer.height)]};
  }

  function sourceGeometry(record) {
    if(record.source) return record.source;
    return record.mode === "rect" ? rectGeometry(record) : lineGeometry(record);
  }

  function applyGeometry(record, geometry) {
    var element = record.element;
    element.classList.add("accessibility-object-detached");
    if (record.mode === "rect") {
      element.style.left = (geometry.x * 100) + "%";
      element.style.top = (geometry.y * 100) + "%";
      element.style.width = (geometry.width * 100) + "%";
      element.style.height = (geometry.height * 100) + "%";
      element.style.transform = "none";
    } else {
      var width = record.article.clientWidth;
      var height = record.article.clientHeight;
      var dx = (geometry.to[0] - geometry.from[0]) * width;
      var dy = (geometry.to[1] - geometry.from[1]) * height;
      element.style.left = (geometry.from[0] * 100) + "%";
      element.style.top = (geometry.from[1] * 100) + "%";
      element.style.width = Math.max(2, Math.hypot(dx, dy)) + "px";
      element.style.transform = "translateY(-50%) rotate(" + Math.atan2(dy, dx) + "rad)";
    }
    positionControls(record, geometry);
  }

  function positionControls(record, geometry) {
    if (!record.controls) return;
    if(record.selector) {
      record.selector.style.left=(geometry.x*100)+'%';record.selector.style.top=(geometry.y*100)+'%';
    }
    if (record.mode === "rect") {
      record.controls.style.left = (geometry.x * 100) + "%";
      record.controls.style.top = (geometry.y * 100) + "%";
      record.controls.style.width = (geometry.width * 100) + "%";
      record.controls.style.height = (geometry.height * 100) + "%";
    } else {
      var points = [geometry.from, geometry.to,
        [(geometry.from[0] + geometry.to[0]) / 2, (geometry.from[1] + geometry.to[1]) / 2]];
      [record.startHandle, record.endHandle, record.moveHandle].forEach(function (handle, index) {
        handle.style.left = (points[index][0] * 100) + "%";
        handle.style.top = (points[index][1] * 100) + "%";
      });
    }
  }

  function showSelected(record) {
    records.forEach(function (item) {
      item.element.classList.toggle("selected-visual-object", item === record);
      if (item.controls) item.controls.hidden = item !== record;
    });
    api.selectVisualObject(slide.id, record.id, record.kind);
  }

  function boundedPoint(point) {
    return [Math.max(0, Math.min(1, rounded(point[0]))),
      Math.max(0, Math.min(1, rounded(point[1])))];
  }

  function startGesture(record, gesture, event) {
    if (!api.isEditMode()) return;
    if(record.kind==='recipe-frame' && gesture==='move' && event.target!==record.element) return;
    event.preventDefault();
    event.stopPropagation();
    // Selection may reveal a midpoint handle beneath the pointer. Keep
    // the gesture's up/click on its original owner instead of the canvas.
    if(event.currentTarget.setPointerCapture) event.currentTarget.setPointerCapture(event.pointerId);
    showSelected(record);
    var initial = objectState[record.id] || sourceGeometry(record);
    var startX = event.clientX;
    var startY = event.clientY;
    var moved = false;
    function onMove(moveEvent) {
      moveEvent.preventDefault();
      var rendered = record.article.getBoundingClientRect();
      var dx = (moveEvent.clientX - startX) / rendered.width;
      var dy = (moveEvent.clientY - startY) / rendered.height;
      if (Math.abs(dx) + Math.abs(dy) < .001 && !moved) return;
      moved = true;
      var next;
      if (record.mode === "rect") {
        next = Object.assign({}, initial);
        if (gesture === "resize") {
          next.width = Math.max(.03, Math.min(1 - initial.x, rounded(initial.width + dx)));
          next.height = Math.max(.012, Math.min(1 - initial.y, rounded(initial.height + dy)));
        } else {
          next.x = Math.max(0, Math.min(1 - initial.width, rounded(initial.x + dx)));
          next.y = Math.max(0, Math.min(1 - initial.height, rounded(initial.y + dy)));
        }
      } else {
        next = {kind: record.kind, from: initial.from.slice(), to: initial.to.slice()};
        if (gesture === "start") next.from = boundedPoint([initial.from[0] + dx, initial.from[1] + dy]);
        else if (gesture === "end") next.to = boundedPoint([initial.to[0] + dx, initial.to[1] + dy]);
        else {
          var minX = Math.min(initial.from[0], initial.to[0]);
          var maxX = Math.max(initial.from[0], initial.to[0]);
          var minY = Math.min(initial.from[1], initial.to[1]);
          var maxY = Math.max(initial.from[1], initial.to[1]);
          dx = Math.max(-minX, Math.min(1 - maxX, dx));
          dy = Math.max(-minY, Math.min(1 - maxY, dy));
          next.from = boundedPoint([initial.from[0] + dx, initial.from[1] + dy]);
          next.to = boundedPoint([initial.to[0] + dx, initial.to[1] + dy]);
        }
      }
      objectState[record.id] = next;
      applyGeometry(record, next);
      api.updateVisualObject(slide.id, record.id, record.kind, next, false);
    }
    function onEnd() {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onEnd);
      document.removeEventListener("pointercancel", onEnd);
      document.body.classList.remove("moving-visual-object");
      if (moved) api.updateVisualObject(slide.id, record.id, record.kind,
        objectState[record.id], true);
    }
    document.body.classList.add("moving-visual-object");
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onEnd);
    document.addEventListener("pointercancel", onEnd);
  }

  records.forEach(function (record) {
    record.element.classList.add("editable-visual-object");
    record.element.setAttribute("data-visual-object-id", record.id);
    record.element.setAttribute("data-visual-object-kind", record.kind);
    record.element.setAttribute("aria-label", record.id + " editable " + record.mode);
    record.element.addEventListener("pointerdown", function (event) {
      startGesture(record, "move", event);
    });
    record.element.addEventListener("click", function (event) {
      if (api.isEditMode()) event.stopPropagation();
    });
    if (record.mode === "rect") {
      var frame = document.createElement("div");
      frame.className = "accessibility-object-frame";
      frame.hidden = true;
      var resize = document.createElement("button");
      resize.type = "button";
      resize.className = "accessibility-object-resize";
      resize.setAttribute("aria-label", "Resize " + record.id);
      resize.addEventListener("pointerdown", function (event) {
        startGesture(record, "resize", event);
      });
      frame.appendChild(resize);
      record.controls = frame;
      frame.addEventListener("click", function (event) { event.stopPropagation(); });
      record.article.appendChild(frame);
      if(record.kind==='recipe-frame') {
        var selector=document.createElement('button');selector.type='button';selector.className='recipe-frame-select';
        selector.textContent='Layout';selector.setAttribute('aria-label','Move layout frame');
        selector.addEventListener('pointerdown',function(event){startGesture(record,'frame',event);});
        selector.addEventListener('click',function(event){event.stopPropagation();});
        record.selector=selector;record.article.appendChild(selector);
      }
    } else {
      var controls = document.createElement("div");
      controls.className = "accessibility-line-controls";
      controls.hidden = true;
      [["start", "accessibility-line-endpoint"], ["end", "accessibility-line-endpoint"],
       ["move", "accessibility-line-move"]].forEach(function (entry) {
        var handle = document.createElement("button");
        handle.type = "button";
        handle.className = entry[1];
        handle.setAttribute("aria-label", entry[0] + " handle for " + record.id);
        handle.addEventListener("pointerdown", function (event) {
          startGesture(record, entry[0], event);
        });
        controls.appendChild(handle);
        if (entry[0] === "start") record.startHandle = handle;
        else if (entry[0] === "end") record.endHandle = handle;
        else record.moveHandle = handle;
      });
      record.controls = controls;
      controls.addEventListener("click", function (event) { event.stopPropagation(); });
      record.article.appendChild(controls);
    }
  });

  requestAnimationFrame(function () {
    records.forEach(function (record) {
      if (objectState[record.id] || record.source) applyGeometry(record, objectState[record.id] || record.source);
      else positionControls(record, sourceGeometry(record));
      if (api.selectedObjectId(slide) === record.id) showSelected(record);
    });
  });
  if (window.ResizeObserver) {
    records.forEach(function (record) {
      var observer = new ResizeObserver(function () {
        if (!record.article.isConnected) { observer.disconnect(); return; }
        var geometry = objectState[record.id] || sourceGeometry(record);
        if (objectState[record.id]) applyGeometry(record, geometry);
        else positionControls(record, geometry);
      });
      observer.observe(record.article);
    });
  }
}


return wireVisualObjects;
}
