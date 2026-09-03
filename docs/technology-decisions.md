# Technology decisions

## Diagram surface: JointJS

The mechanism recipe uses the open-source JointJS core plus its
DirectedGraph/Dagre layout package. JointJS supplies the behavior a slide
diagram actually needs: semantic node and edge models, ports, SVG rendering,
orthogonal/Manhattan routing, dragging, and automatic link rerouting.

ELK.js was tested against the same graph. It produced a good initial layout but
is intentionally only a layout engine; using it alone would leave selection,
movement, rerouting, and editor integration for this project to rebuild. ELK
remains a sensible future layout option behind the same recipe boundary for
graphs whose constraints exceed Dagre.

Primary references:

- [JointJS documentation](https://docs.jointjs.com/)
- [JointJS directed graph layout](https://docs.jointjs.com/learn/features/automatic-layouts/directed-graph/)
- [JointJS link routing](https://docs.jointjs.com/learn/features/diagram-basics/links/)
- [ELK.js repository](https://github.com/kieler/elkjs)

## Vector geometry: JSXGraph plus KaTeX

Mechanism topology and mathematical geometry are different visual problems.
JointJS remains the mechanism engine; vector-space slides use JSXGraph so
arrows, projections, perpendicular components, arcs, and equal-aspect bounds
live in a real coordinate system rather than an auto-layout graph. JSXGraph
owns containment and mathematical construction. KaTeX owns every displayed
formula and symbol, so slide authors never fake mathematics with Unicode or
HTML spacing.

This replaces the earlier attempt to express the Exp81 vector construction as
a row of process boxes. A small native SVG layer could draw one such picture,
but it would recreate coordinate transforms, aspect preservation, geometry
primitives, and interaction already maintained upstream.

Primary references:

- [JSXGraph documentation](https://jsxgraph.org/docs/)
- [JSXGraph Arrow](https://jsxgraph.org/docs/symbols/Arrow.html)
- [JSXGraph source](https://github.com/jsxgraph/jsxgraph)
- [KaTeX documentation](https://katex.org/docs/api)

## Gallery browsing: native controls and local view state

Swiper, Embla, and PhotoSwipe are mature choices for generic carousels and
lightboxes. The scientific gallery's hard problem is different: several
hierarchical selectors choose a matched evidence view, a prominent metric must
change with that view, and the selected facet/page must survive slide
navigation. Native CSS grids, `contain`, ordinary buttons, and localStorage
provide that behavior with no carousel abstraction or event bridge.

The recipe may adopt Embla later if touch momentum or very large virtualized
image rails become a measured need. The current implementation deliberately
keeps navigation state semantic (`class`, `method`, `dose`, `page`) rather than
reducing it to a single carousel index.

Primary references:

- [Embla Carousel API](https://www.embla-carousel.com/docs/v8/api/)
- [Swiper API](https://swiperjs.com/swiper-api)
- [PhotoSwipe data sources](https://photoswipe.com/data-sources/)
