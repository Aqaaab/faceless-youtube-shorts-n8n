from __future__ import annotations

from .models import ResearchBundle


class FactValidationError(ValueError):
    pass


NUMERIC_FIELDS = {
    "horsepower", "torque", "acceleration_0_60", "top_speed", "engine_displacement",
    "battery_capacity", "range", "weight", "production_count", "model_year"
}


def validate_research(bundle: ResearchBundle) -> ResearchBundle:
    source_ids = {source.source_id for source in bundle.sources}
    for fact in bundle.facts:
        if any(e.source_id not in source_ids for e in fact.evidence):
            raise FactValidationError(f"Fact has evidence referencing an unknown source: {fact.claim}")
        if not fact.evidence or not any(e.supports for e in fact.evidence):
            raise FactValidationError(f"Unsupported fact: {fact.claim}")
        if fact.field in NUMERIC_FIELDS and fact.confidence < 0.85:
            raise FactValidationError(f"Low-confidence numeric fact blocked: {fact.claim}")
        fact.status = "VERIFIED"
    return bundle


def approved_claims(bundle: ResearchBundle) -> list[ResearchFact]:
    validate_research(bundle)
    return [fact for fact in bundle.facts if fact.status == "VERIFIED"]
