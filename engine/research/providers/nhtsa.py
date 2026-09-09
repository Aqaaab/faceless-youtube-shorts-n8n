from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..models import Evidence, ResearchBundle, ResearchFact, Source

BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"


class NHTSAProvider:
    name = "nhtsa-vpic"

    def healthcheck(self) -> bool:
        return True

    def search(self, make: str, model: str, year: int | None = None) -> ResearchBundle:
        query = urllib.parse.urlencode({"format": "json", "modelyear": year or "", "make": make, "model": model})
        url = f"{BASE_URL}/GetModelsForMake/{urllib.parse.quote(make)}?{query}"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                payload = json.load(response)
        except Exception as exc:
            raise RuntimeError(f"NHTSA request failed: {exc}") from exc

        now = datetime.now(timezone.utc).isoformat()
        source = Source(
            source_id="nhtsa-vpic",
            url=url,
            publisher="NHTSA",
            title="NHTSA vPIC vehicle data",
            retrieved_at=now,
            authority=0.95,
        )
        facts: list[ResearchFact] = []
        results = payload.get("Results", [])
        for row in results[:25]:
            name = row.get("Model_Name") or row.get("ModelName")
            if not name or model.lower() not in str(name).lower():
                continue
            facts.append(
                ResearchFact(
                    claim=f"NHTSA identifies model {name} for make {make}",
                    field="model_name",
                    value=str(name),
                    evidence=[Evidence(source_id=source.source_id, excerpt=json.dumps(row, ensure_ascii=False), supports=True)],
                    confidence=0.95,
                )
            )
        return ResearchBundle(topic=f"{make} {model}", sources=[source], facts=facts)
