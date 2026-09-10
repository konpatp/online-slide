"""A new browser regression cannot silently miss the shared runner."""
# test-tier: every-time
import unittest
from tools.run_browser_checks import discover


class BrowserCheckDiscoveryTests(unittest.TestCase):
    def test_every_tool_declares_its_execution_boundary(self):
        checks = discover()
        self.assertEqual(checks['save_lifecycle'][1], 'scratch')
        self.assertEqual(checks['text_boxes'][1], 'scratch')
        self.assertEqual(checks['runtime_update'][1], 'scratch-output')
        self.assertEqual(checks['live_editor'][1], 'read-only-probe')
        self.assertEqual(checks['gallery_layout'][1], 'read-only-probe')
