# test-tier: every-time
"""Sparse pages may not let height-derived image widths escape their pair."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_sparse_pair_stays_inside_its_column():
    css = (Path(__file__).resolve().parents[1]/'public/styles.css').read_text()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1920,'height':1080})
        page.set_content('<style>'+css+'</style><div class="paired-gallery-wall" '
            'style="width:1724px;height:700px;--pair-columns:3;--pair-rows:2">'+
            ''.join('<div class="paired-gallery-group"><div class="paired-gallery-headings">Pair</div>'+
                ''.join('<div class="gallery-pair"><div class="gallery-pair-pictures">'
                    '<div class="gallery-cell"></div><div class="gallery-cell"></div>'
                    '</div><div class="gallery-pair-caption-frame">Class</div></div>' for _ in range(2))+
                '</div>' for _ in range(3))+'</div>')
        assert page.locator('.gallery-cell').evaluate_all("""ns=>ns.every(n=>{
            const a=n.getBoundingClientRect(),b=n.closest('.paired-gallery-group').getBoundingClientRect();
            return a.width>0 && a.left>=b.left-1 && a.right<=b.right+1;
        })""")
        browser.close()
