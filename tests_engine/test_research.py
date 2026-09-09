import unittest

from engine.research.models import Evidence, ResearchBundle, ResearchFact, Source
from engine.research.validator import FactValidationError, validate_research


class ResearchValidationTests(unittest.TestCase):
    def source(self):
        return Source(source_id="s1", url="https://example.test", publisher="Test", title="Test source", retrieved_at="2026-01-01T00:00:00Z", authority=1.0)

    def test_supported_numeric_fact_is_verified(self):
        bundle = ResearchBundle(
            topic="car",
            sources=[self.source()],
            facts=[ResearchFact(claim="100 hp", field="horsepower", value=100, unit="hp", confidence=0.95, evidence=[Evidence(source_id="s1", excerpt="100 hp", supports=True)])],
        )
        validate_research(bundle)
        self.assertEqual(bundle.facts[0].status, "VERIFIED")

    def test_numeric_fact_without_strong_confidence_is_blocked(self):
        bundle = ResearchBundle(
            topic="car",
            sources=[self.source()],
            facts=[ResearchFact(claim="100 hp", field="horsepower", value=100, unit="hp", confidence=0.7, evidence=[Evidence(source_id="s1", excerpt="100 hp", supports=True)])],
        )
        with self.assertRaises(FactValidationError):
            validate_research(bundle)

    def test_missing_evidence_is_blocked(self):
        bundle = ResearchBundle(
            topic="car",
            sources=[self.source()],
            facts=[ResearchFact(claim="unknown", field="horsepower", value=100, confidence=0.99, evidence=[Evidence(source_id="s1", excerpt="not supportive", supports=False)])],
        )
        with self.assertRaises(FactValidationError):
            validate_research(bundle)

    def test_unknown_source_reference_is_blocked(self):
        bundle = ResearchBundle(
            topic="car",
            sources=[self.source()],
            facts=[ResearchFact(claim="100 hp", field="horsepower", value=100, confidence=0.99, evidence=[Evidence(source_id="missing", excerpt="100 hp", supports=True)])],
        )
        with self.assertRaises(FactValidationError):
            validate_research(bundle)


if __name__ == "__main__":
    unittest.main()
