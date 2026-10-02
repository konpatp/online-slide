"""Agent-authoring helpers share the build's rules and the renderer's metrics."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_deck import check_sources
from slide_templates import AUTHOR_STARTERS, STARTERS, make_starter
from slidekit import ContractError
from slidekit.fit import describe, headline_fit, headline_metrics


class StarterTests(unittest.TestCase):
    def test_every_starter_is_valid_with_a_footer(self):
        for recipe in [*STARTERS, *AUTHOR_STARTERS]:
            spec = make_starter(recipe, 'starter', '2026-01-01T00:00:00Z', authoring=True, footer=True)
            self.assertEqual(spec['components'][spec['footer']]['role'], 'protocol')

    def test_chart_starter_is_for_authoring_not_the_picker(self):
        with self.assertRaises(ContractError):
            make_starter('chart-panels', 'starter', '2026-01-01T00:00:00Z')
        spec = make_starter('chart-panels', 'starter', '2026-01-01T00:00:00Z', authoring=True)
        figure = spec['components'][spec['data']['panels'][0]['chart']]['figure']
        self.assertTrue(figure['data'][0]['uid'])
        self.assertTrue(figure['layout']['annotations'][0]['name'])


class SourceCheckTests(unittest.TestCase):
    def test_check_reports_the_builds_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            (source / 'slides').mkdir()
            first = make_starter('section-divider', 'first', '2026-01-01T00:00:00Z')
            (source / 'slides/first.json').write_text(json.dumps(first))
            catalog, _ = check_sources(source)
            self.assertTrue(catalog)
            spec = make_starter('evidence-figure', 'orphan', '2026-01-01T00:00:00Z', after='missing')
            (source / 'slides/orphan.json').write_text(json.dumps(spec))
            with self.assertRaisesRegex(ContractError, 'placement anchor'):
                check_sources(source)


@unittest.skipUnless(shutil.which('fc-match'), 'fontconfig resolves the renderer font')
class FitTests(unittest.TestCase):
    def test_metrics_come_from_the_stylesheet(self):
        metrics = headline_metrics()
        self.assertAlmostEqual(metrics['font_px'], 1920 * 0.0315, places=2)
        self.assertGreater(metrics['max_width_px'], 1000)

    def test_wrap_and_capacity(self):
        short = headline_fit('Loops win')
        self.assertEqual(short['lines'], 1)
        long = headline_fit('loops ' * 60)
        self.assertGreater(long['lines'], 2)
        self.assertEqual(headline_fit('one\ntwo')['lines'], 2)
        self.assertLess(headline_fit('loops ' * 30, scale=0.5)['lines'], headline_fit('loops ' * 30)['lines'])
        self.assertIn('characters fit on one line', describe(short))


if __name__ == '__main__':
    unittest.main()
