export const scientificRecipeGuides = {
    "slide-index": {use:"Navigate a deck without duplicating its mutable order or visibility.",owns:"Section labels, semantic route links, current-order sorting, and revision-safe per-slide/section visibility controls."},
    "evidence-figure": {use:"Show a retained scientific figure without changing its pixels.",owns:"A contained, uncropped image region, up to four aligned labels, and a bounded caption."},
    "hero-equation": {use:"Introduce one organizing relation.",owns:"A dominant fitted LaTeX region, aligned local definitions, and an optional question region."},
    "section-divider": {use:"Mark a change of question or method.",owns:"One bounded, vertically centered headline region; optional eyebrow and protocol."},
    "chart-panels": {use: "Compare source-native scientific plots, singly or in aligned panels.", owns: "Bounded plot regions, shared axis regions, native log axes, hover, zoom, export, and semantic annotation editing."},
    "hero-plot": {use: "Compare measured trajectories on one pair of axes.", owns: "Plot region, axes, legend, series styling, and protocol placement."},
    "evidence-table": {use: "Compare aligned values and emphasize selected cells.", owns: "Column alignment, padded cells, bounded whole-table fitting, and native table editing."},
    "mechanism-pipeline": {use: "Explain a process through connected states or models.", owns: "Node sizing, ranked layout, connector routing, and fitted text regions."},
    "vector-geometry": {use: "Explain vectors, projections, angles, and equal-norm constructions.", owns: "Equal-aspect coordinates, proportional scaling, vector handles, and bounded math labels. Authors supply meaningful geometry."},
    "hierarchical-gallery": {use: "Explore images by facets and identity pages.", owns: "Image regions, compact controls, fitted captions, metric placement, and persistent selection."},
    "segment-chain": {use:"Show which segments of a chain of states a procedure supervises, optionally stepped once by an explicit Play.",owns:"Node and segment geometry, shared horizontal alignment across rows, supervised highlighting, TeX end labels, and a one-shot Play with no autoplay."},
    "track-diagram": {use:"Compare how a teacher rollout supervises a student path: which student states are supervised, and where a teacher state feeds or checks them.",owns:"Shared position axis across teacher and student tracks, supervised endpoints and spans, dashed teacher-to-student links, brackets, and bounded labels."},
    "compute-grid": {use:"Show two training designs that spend the same compute per step: tiles are network passes, rows are images, red nodes are supervised states.",owns:"Equal tile geometry across blocks, per-image chains of passes with supervised endpoints, an optional teacher/student intuition strip, and matched / not-matched note lines."},
    "target-accessibility": {use: "Compare qualitative target decompositions and model reach.", owns: "Aligned signal regions, reach marks, shared legend, and bounded labels."}
  };

