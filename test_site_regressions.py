"""搜尋覆蓋與審閱紀錄回歸測試：python -m unittest test_site_regressions.py。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build_site as site


class SiteRegressions(unittest.TestCase):
    def test_unknown_review_is_not_invented(self):
        with patch.object(site, 'REVIEW_DATES', {}):
            rendered = site.page('測試', '測試', 'calc.html', '', {'@type': 'MedicalWebPage'})
        self.assertNotIn('lastReviewed', rendered)
        self.assertNotIn('醫師審閱於', rendered)

    def test_review_stays_fixed_when_build_date_changes(self):
        with patch.object(site, 'REVIEW_DATES', {'calc.html': '2026-09-01'}), patch.object(site, 'TODAY', '2027-01-01'):
            rendered = site.page('測試', '測試', 'calc.html', '', {'@type': 'MedicalWebPage'})
        self.assertIn('醫師審閱於 2026-09-01', rendered)
        self.assertIn('"lastReviewed": "2026-09-01"', rendered)
        self.assertNotIn('醫師審閱於 2027', rendered)

    def test_all_papers_searchable_with_working_anchors(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'search.json'
            with patch.object(site, 'SEARCH_INDEX', output):
                site.build_search_index([], [], [])
            entries = json.loads(output.read_text(encoding='utf-8'))
        for paper in site.PAPERS:
            row = next(x for x in entries if x['t'] == paper['zh'])
            path, anchor = row['u'].split('#')
            self.assertIn('id="' + anchor + '"', (site.ROOT / path.lstrip('/')).read_text(encoding='utf-8'))
            self.assertIn(paper['en'], row['b'])
            if paper.get('doi'):
                self.assertIn(paper['doi'], row['b'])

    def test_review_dates_reject_bad_and_future_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reviewed.json'
            for value in ['2026-02-30', '2099-01-01', 'today']:
                path.write_text(json.dumps({'calc.html': value}), encoding='utf-8')
                with patch.object(site, 'REVIEW_DATES_FILE', path), self.assertRaises(ValueError):
                    site.load_review_dates()


if __name__ == '__main__':
    unittest.main()
