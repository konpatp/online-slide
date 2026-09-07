/* Read-only discovery: no registrations, state saves, or retained preview cache. */
(async function () {
  "use strict";
  const root = document.getElementById("catalog");
  const urls = [];
  function node(tag, text, parent) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (parent) parent.appendChild(element);
    return element;
  }
  try {
    const response = await fetch("api/deck-state");
    if (!response.ok) throw new Error("Deck unavailable: " + response.status);
    const deck = await response.json();
    root.replaceChildren();
    const grouped = {};
    Object.values(deck.slides).forEach(slide => (grouped[slide.recipe] ||= []).push(slide));
    Object.entries(window.scientificRecipeGuides).forEach(([id, guide]) => {
      const section = node("section", "", root);
      section.id = id;
      node("h2", id.replaceAll("-", " "), section);
      node("p", guide.use, section);
      node("p", "Layout owns: " + guide.owns, section);
      const examples = node("div", "", section); examples.className = "examples";
      if (!grouped[id]) node("p", "No example in this deck yet.", examples);
      (grouped[id] || []).forEach(slide => {
        const item = node("article", "", examples); item.className = "example";
        const preview = node("div", "", item); preview.className = "preview";
        const button = node("button", "Load live preview", preview);
        button.type = "button";
        const href = "./?present=1#" + encodeURIComponent(slide.id);
        button.addEventListener("click", () => {
          const frame = document.createElement("iframe");
          frame.title = slide.components[slide.headline].text;
          frame.src = href; frame.tabIndex = -1;
          frame.addEventListener("load", () => {
            const exit = frame.contentDocument.querySelector("[data-presentation-exit]");
            if (exit) exit.style.display = "none";
          });
          preview.replaceChildren(frame);
        }, {once:true});
        node("h3", slide.components[slide.headline].text, item);
        const links = node("div", "", item); links.className = "links";
        const open = node("a", "Open slide", links); open.href = href;
        const source = node("a", "Download source", links);
        const url = URL.createObjectURL(new Blob([JSON.stringify(slide, null, 2)+"\n"], {type:"application/json"}));
        urls.push(url); source.href = url; source.download = slide.id + ".json";
        node("p", "Inputs: " + Object.keys(slide.data).join(", "), item);
      });
    });
  } catch (error) { root.textContent = "Cannot load catalog: " + error.message; }
  addEventListener("pagehide", () => urls.forEach(url => URL.revokeObjectURL(url)), {once:true});
}());
