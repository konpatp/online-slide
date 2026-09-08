import katex from "katex";
import "katex/dist/katex.min.css";

function renderLatex(host, source, options = {}) {
  katex.render(source, host, {
    displayMode: Boolean(options.displayMode),
    throwOnError: false,
    strict: "warn",
    trust: false,
  });
  host.dataset.mathEngine = "katex";
}

window.ScientificMathRuntime = { renderLatex };
