"""Regression: source-bound JSON approvals must not spend WAV render quota."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'deploy' / 'metric-mix'


class PlanNginxLimits(unittest.TestCase):
    def test_strategy_submissions_have_their_own_bounded_quota(self):
        locations = (ROOT / 'harbeat-metric-mix.conf').read_text()
        zones = (ROOT / '00-harbeat-metric-mix-limit.conf').read_text()
        plan = re.search(r'location = /listen/smart-api/plans \{(.*?)\n\}', locations, re.S).group(1)
        render = re.search(r'location = /listen/smart-api/jobs \{(.*?)\n\}', locations, re.S).group(1)
        self.assertIn('zone=harbeat_metric_plans', plan)
        self.assertIn('zone=harbeat_metric_jobs', render)
        self.assertIn('zone=harbeat_metric_jobs:5m rate=6r/m;', zones)
        self.assertIn('zone=harbeat_metric_plans:5m rate=30r/m;', zones)
        self.assertIn('error_page 429 = @harbeat_plan_limited;', plan)
        self.assertIn('add_header Retry-After "10" always;', locations)


if __name__ == '__main__':
    unittest.main()
