/* The demo client has no framework or build step on purpose. */
(function () {
  "use strict";

  var stage = document.querySelector("[data-stage]");
  var thumbList = document.querySelector("[data-thumb-list]");
  var count = document.querySelector("[data-slide-count]");
  var position = document.querySelector("[data-position]");
  var status = document.querySelector("[data-save-state]");
  var editToggle = document.querySelector("[data-edit-toggle]");
  var undoButton = document.querySelector("[data-undo]");
  var toast = document.querySelector("[data-toast]");
  var state = null;
  var accepted = null;
  var currentId = null;
  var editMode = false;
  var pending = null;
  var inFlight = null;
  var undoBase = null;
  var inputTimer = null;
  var toastTimer = null;

  function copy(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function snapshot(value) {
    return {
      schema: value.schema,
      order: value.order.slice(),
      hidden: value.hidden.slice(),
      slides: copy(value.slides)
    };
  }

  function sameSnapshot(a, b) {
    return JSON.stringify(snapshot(a)) === JSON.stringify(snapshot(b));
  }

  function setStatus(label, kind) {
    status.textContent = label;
    status.className = "save-state " + (kind || "saved");
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("visible"); }, 2700);
  }

  function slideAt(index) {
    return state.slides[state.order[index]];
  }

  function currentIndex() {
    var index = state.order.indexOf(currentId);
    return index < 0 ? 0 : index;
  }

  function renderStage() {
    var index = currentIndex();
    currentId = state.order[index];
    var slide = slideAt(index);
    stage.textContent = "";

    var canvas = document.createElement("article");
    canvas.className = "slide-canvas";
    canvas.style.setProperty("--accent", slide.accent);
    canvas.setAttribute("data-slide-id", currentId);
    if (state.hidden.indexOf(currentId) >= 0) {
      var ribbon = document.createElement("span");
      ribbon.className = "hidden-ribbon";
      ribbon.textContent = "Hidden from presentation";
      canvas.appendChild(ribbon);
    }

    var content = document.createElement("div");
    content.className = "slide-content";
    var kicker = document.createElement("div");
    kicker.className = "slide-kicker";
    kicker.textContent = "ONLINE-SLIDE / DEMO";
    content.appendChild(kicker);

    var title = document.createElement("h1");
    title.className = "slide-title";
    title.textContent = slide.title;
    title.contentEditable = editMode ? "true" : "false";
    title.setAttribute("data-field", "title");
    title.setAttribute("aria-label", "Slide title");
    content.appendChild(title);

    var body = document.createElement("p");
    body.className = "slide-body";
    body.textContent = slide.body;
    body.contentEditable = editMode ? "true" : "false";
    body.setAttribute("data-field", "body");
    body.setAttribute("aria-label", "Slide body");
    content.appendChild(body);
    canvas.appendChild(content);

    var meta = document.createElement("div");
    meta.className = "slide-meta";
    meta.textContent = "Slide " + String(index + 1).padStart(2, "0") + "  ·  " + currentId;
    canvas.appendChild(meta);
    var orb = document.createElement("div");
    orb.className = "slide-orb";
    orb.setAttribute("aria-hidden", "true");
    canvas.appendChild(orb);
    stage.appendChild(canvas);
    stage.classList.toggle("edit-mode", editMode);
    position.textContent = (index + 1) + " / " + state.order.length;
    document.querySelector("[data-prev]").disabled = index === 0;
    document.querySelector("[data-next]").disabled = index === state.order.length - 1;

    [title, body].forEach(function (field) {
      field.addEventListener("input", function () {
        if (!editMode) return;
        state.slides[currentId][field.getAttribute("data-field")] = field.textContent.trim();
        beginChange();
        clearTimeout(inputTimer);
        inputTimer = setTimeout(persist, 280);
      });
    });
  }

  function renderThumbs() {
    thumbList.textContent = "";
    count.textContent = String(state.order.length);
    state.order.forEach(function (id, index) {
      var slide = state.slides[id];
      var card = document.createElement("article");
      card.className = "thumb" + (id === currentId ? " current" : "") +
        (state.hidden.indexOf(id) >= 0 ? " hidden" : "");
      card.setAttribute("data-id", id);

      var number = document.createElement("div");
      number.className = "thumb-index";
      number.textContent = String(index + 1).padStart(2, "0");
      card.appendChild(number);
      var inner = document.createElement("div");
      inner.className = "thumb-card";
      var art = document.createElement("div");
      art.className = "thumb-art";
      art.style.setProperty("--thumb-accent", slide.accent);
      var kicker = document.createElement("div");
      kicker.className = "thumb-kicker";
      kicker.textContent = "DEMO";
      var title = document.createElement("div");
      title.className = "thumb-title";
      title.textContent = slide.title;
      art.appendChild(kicker);
      art.appendChild(title);
      inner.appendChild(art);

      var actions = document.createElement("div");
      actions.className = "thumb-actions";
      [
        ["↑", "move", -1, "Move earlier"],
        ["↓", "move", 1, "Move later"],
        [state.hidden.indexOf(id) >= 0 ? "◉" : "◌", "visibility", null,
          state.hidden.indexOf(id) >= 0 ? "Show slide" : "Hide slide"]
      ].forEach(function (item) {
        var button = document.createElement("button");
        button.className = "thumb-action " + item[1];
        button.type = "button";
        button.textContent = item[0];
        button.setAttribute("aria-label", item[3]);
        button.setAttribute("data-action", item[1]);
        if (item[2] !== null) button.setAttribute("data-delta", item[2]);
        actions.appendChild(button);
      });
      inner.appendChild(actions);
      card.appendChild(inner);
      thumbList.appendChild(card);
    });
  }

  function render() {
    renderStage();
    renderThumbs();
    undoButton.disabled = !undoBase;
    editToggle.textContent = editMode ? "Done editing" : "Enable edit";
    editToggle.classList.toggle("active", editMode);
  }

  function beginChange() {
    if (!undoBase) undoBase = copy(accepted);
    undoButton.disabled = false;
    setStatus("Saving…", "saving");
  }

  function persist() {
    pending = snapshot(state);
    setStatus("Saving…", "saving");
    flush();
  }

  function flush() {
    if (inFlight || !pending) return;
    var job = pending;
    pending = null;
    inFlight = job;
    fetch("api/deck-state", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({baseRevision: accepted.revision, snapshot: job})
    }).then(function (response) {
      return response.json().then(function (payload) {
        return {ok: response.ok, status: response.status, payload: payload};
      });
    }).then(function (result) {
      inFlight = null;
      if (!result.ok) {
        if (result.status === 409 && result.payload.state) {
          accepted = result.payload.state;
          state = copy(accepted);
          pending = null;
          undoBase = null;
          render();
          setStatus("Conflict · reloaded", "error");
          showToast("Another editor saved first; their snapshot is now shown.");
        } else {
          pending = job;
          setStatus("Offline · retrying", "error");
          setTimeout(flush, 1400);
        }
        return;
      }
      accepted = result.payload;
      if (!pending && sameSnapshot(state, accepted)) {
        state = copy(accepted);
        undoBase = null;
        render();
        setStatus("Saved", "saved");
      } else {
        setStatus("Saving…", "saving");
        flush();
      }
    }).catch(function () {
      inFlight = null;
      pending = job;
      setStatus("Offline · retrying", "error");
      setTimeout(flush, 1400);
    });
  }

  function mutateOrder(id, delta) {
    if (!editMode) return;
    var index = state.order.indexOf(id);
    var target = index + delta;
    if (index < 0 || target < 0 || target >= state.order.length) return;
    beginChange();
    var moved = state.order.splice(index, 1)[0];
    state.order.splice(target, 0, moved);
    currentId = id;
    render();
    persist();
  }

  function toggleHidden(id) {
    if (!editMode) return;
    beginChange();
    var index = state.hidden.indexOf(id);
    if (index >= 0) state.hidden.splice(index, 1);
    else state.hidden.push(id);
    render();
    persist();
  }

  function select(id) {
    if (state.order.indexOf(id) < 0) return;
    currentId = id;
    render();
  }

  function step(delta) {
    var next = Math.max(0, Math.min(state.order.length - 1, currentIndex() + delta));
    currentId = state.order[next];
    render();
  }

  function undo() {
    if (!undoBase) return;
    state = copy(undoBase);
    currentId = state.order[0];
    undoBase = null;
    render();
    persist();
    showToast("Reverted the last edit burst.");
  }

  thumbList.addEventListener("click", function (event) {
    var card = event.target.closest("[data-id]");
    if (!card) return;
    var id = card.getAttribute("data-id");
    var action = event.target.closest("[data-action]");
    if (!action) { select(id); return; }
    event.preventDefault();
    if (action.getAttribute("data-action") === "move") {
      mutateOrder(id, Number(action.getAttribute("data-delta")));
    } else if (action.getAttribute("data-action") === "visibility") {
      toggleHidden(id);
    }
  });

  document.querySelector("[data-prev]").addEventListener("click", function () { step(-1); });
  document.querySelector("[data-next]").addEventListener("click", function () { step(1); });
  editToggle.addEventListener("click", function () {
    editMode = !editMode;
    render();
    if (editMode) showToast("Edit mode on — the canvas is ready for typing.");
  });
  undoButton.addEventListener("click", undo);
  document.addEventListener("keydown", function (event) {
    if (event.target && event.target.isContentEditable) return;
    if (event.key === "ArrowLeft") step(-1);
    if (event.key === "ArrowRight") step(1);
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      undo();
    }
  });

  fetch("api/deck-state", {headers: {"Accept": "application/json"}})
    .then(function (response) {
      if (!response.ok) throw new Error("could not load deck");
      return response.json();
    })
    .then(function (payload) {
      state = copy(payload);
      accepted = copy(payload);
      currentId = state.order[0];
      render();
    })
    .catch(function () {
      setStatus("Could not load", "error");
      showToast("The demo server is not reachable. Start server.py first.");
    });
}());
