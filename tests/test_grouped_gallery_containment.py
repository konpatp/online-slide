# test-tier: every-time
"""Grouped cells keep their image sub-grid and caption inside each grid cell."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_grouped_cells_stay_inside_their_grid_cell_and_caption_does_not_cover_images():
    css = (Path(__file__).resolve().parents[1]/'public/styles.css').read_text()
    cell = ('<div class="gallery-cell-group"><div class="gallery-group-images" '
            'style="--group-columns:2;--group-rows:2">' + '<div class="gallery-cell"></div>'*4 +
            '</div><div class="gallery-group-caption-frame"><div class="gallery-group-caption">R8·K4 · FID 27.4 · +14%</div></div></div>')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.set_content('<style>'+css+'</style><div class="hierarchical-gallery-body grouped-gallery" '
            'style="position:absolute;left:96px;right:96px"><div class="gallery-controls"></div>'
            '<div class="gallery-summary"></div><div class="hierarchical-gallery-view">'
            '<div class="hierarchical-gallery-grid" style="--gallery-columns:3;--gallery-rows:2">'
            '<div class="gallery-corner"></div>' + '<div class="gallery-heading-region">S</div>'*3 +
            ('<div class="gallery-identity-region">Row</div>' + cell*3)*2 + '</div></div></div>')
        ok = page.evaluate("""() => [...document.querySelectorAll('.gallery-cell-group')].every(g => {
            const b = g.getBoundingClientRect(), t = g.querySelector('.gallery-group-images').getBoundingClientRect(),
                  c = g.querySelector('.gallery-group-caption-frame').getBoundingClientRect();
            const tiles = [...g.querySelectorAll('.gallery-cell')].map(n => n.getBoundingClientRect());
            return t.width > 250 && t.left >= b.left-1 && t.right <= b.right+1 && c.top >= t.bottom-1 &&
                   c.bottom <= b.bottom+1 && tiles.every(r => r.width > 120 && Math.abs(r.width-r.height) < 2);
        })""")
        assert ok
        browser.close()
