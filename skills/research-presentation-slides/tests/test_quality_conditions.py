"""研究固有の数値を使わず、主張に必要な条件の保持と検査の限界を確認する。"""
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

from test_quality import base, shape, write_pptx
from check_layout import check


class ClaimConditionTests(unittest.TestCase):
    def inspect_claims(self, claims, visible='Synthetic claim'):
        with tempfile.TemporaryDirectory() as directory:
            pptx = Path(directory) / 'fixture.pptx'
            write_pptx(pptx, [base() + shape(4, 'claim', 'body', visible)])
            return check(pptx, deck_spec={'slides': [{'semantic_claims': claims}]},
                         layout={'slides': [{'number': 1, 'expected_elements': []}]})

    def codes(self, report, status=None):
        return {f['code'] for f in report['findings']
                if status is None or f['status'] == status}

    def claim(self, **conditions):
        return {'text': 'Synthetic claim', 'source': 'Fictional study, table 2',
                'status': 'illustrative', **conditions}

    def test_full_sample_does_not_satisfy_declared_subgroup_denominator(self):
        claim = self.claim(denominator='subgroup: 40 trials')
        report = self.inspect_claims([claim], 'Synthetic claim; full sample: 200 trials')
        self.assertIn('claim_condition', self.codes(report, 'error'))
        report = self.inspect_claims([claim], 'Synthetic claim; subgroup: 40 trials')
        self.assertNotIn('claim_condition', self.codes(report))
        self.assertIn('source_meaning', self.codes(report, 'review_required'))

    def test_period_and_population_cannot_be_dropped_by_shortening(self):
        claim = self.claim(subject='participating laboratories', period='2024 collection')
        report = self.inspect_claims([claim], 'Synthetic claim; participating laboratories')
        self.assertIn('claim_condition', self.codes(report, 'error'))
        report = self.inspect_claims([claim],
                                    'Synthetic claim; participating laboratories; 2024 collection')
        self.assertNotIn('claim_condition', self.codes(report))

    def test_qualitative_plan_does_not_need_numeric_fields(self):
        report = self.inspect_claims([{'text': 'Synthetic claim', 'source': 'Fictional protocol',
                                       'status': 'plan'}])
        self.assertNotIn('claim_condition', self.codes(report))
        self.assertNotIn('claim_schema', self.codes(report))

    def test_invalid_conditions_are_findings_not_guessed_strings(self):
        for value in [40, True, [], {}, '']:
            with self.subTest(value=value):
                self.assertIn('claim_schema', self.codes(
                    self.inspect_claims([self.claim(denominator=value)]), 'error'))
        for value in ['a claim', [None]]:
            with self.subTest(value=value):
                self.assertIn('claim_schema', self.codes(self.inspect_claims(value), 'error'))

    def test_text_equality_never_proves_source_scope(self):
        # Even matching declarations can have been transcribed incorrectly.
        report = self.inspect_claims([self.claim(subject='all users')],
                                    'Synthetic claim; all users')
        self.assertNotIn('claim_condition', self.codes(report))
        self.assertIn('source_meaning', self.codes(report, 'review_required'))

    def test_structured_evidence_is_checked_but_preparation_is_not_speaker_content(self):
        with tempfile.TemporaryDirectory() as directory:
            pptx = Path(directory) / 'fixture.pptx'
            write_pptx(pptx, [base()])
            spec = {'slides': [{'notes': {'evidence': ['Fictional source section 3'],
                                          'preparation': ['Check the source transcription']}}]}
            report = check(pptx, deck_spec=spec,
                           layout={'slides': [{'number': 1, 'expected_elements': []}]})
            missing = [f for f in report['findings'] if f['code'] == 'notes_required']
            self.assertEqual(len(missing), 1)
            self.assertIn('Fictional source section 3', missing[0]['message'])

    def test_layout_report_cannot_overwrite_independent_input(self):
        with tempfile.TemporaryDirectory() as directory:
            pptx = Path(directory) / 'fixture.pptx'
            spec = Path(directory) / 'input.json'
            write_pptx(pptx, [base()])
            original = '{"slides": [{"id": "example"}]}'
            spec.write_text(original)
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                                     'scripts/check_layout.py'), str(pptx), '--deck-spec', str(spec),
                                     '--report', str(spec)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(spec.read_text(), original)


if __name__ == '__main__':
    unittest.main()
