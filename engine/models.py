from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

VisualMode = Literal["NORMAL", "BLUEPRINT", "X_RAY", "CUTAWAY", "FLOW", "EXPLODED", "TECHNICAL"]
MediaType = Literal["video", "image", "svg", "generated"]


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1)
    source: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class AudioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    music: bool = False
    sfx: list[str] = Field(default_factory=list)
    voice_required: bool = True


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: int = Field(ge=1, le=25)
    title: str = Field(min_length=1)
    narration: str = Field(min_length=1)
    duration: float = Field(gt=0)
    facts: list[str] = Field(default_factory=list)
    component: str = Field(min_length=1)
    visual_profile: str = Field(min_length=1)
    visual_mode: VisualMode
    media_query: str = Field(min_length=1)
    media_type: MediaType
    transition: str = Field(min_length=1)
    subtitle: str = Field(min_length=1)
    audio: AudioPlan = Field(default_factory=AudioPlan)


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1)
    vehicle: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target_duration_seconds: int = Field(ge=420, le=900)


class Research(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list)
    methodology: str = Field(min_length=1)


class VisualPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_mode: VisualMode = "TECHNICAL"
    component_registry_version: str = Field(min_length=1)


class Short(BaseModel):
    model_config = ConfigDict(extra="forbid")
    short_id: int = Field(ge=1, le=4)
    title: str = Field(min_length=1)
    scene_ids: list[int] = Field(min_length=1)
    duration: float = Field(gt=0)
    hook: str = Field(min_length=1)
    technical_reveal: str = Field(min_length=1)
    payoff: str = Field(min_length=1)
    ending: str = Field(min_length=1)


class QAReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["PENDING", "PASS", "BLOCKED"] = "PENDING"
    critical_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EpisodeBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    episode: Episode
    research: Research
    facts: list[Fact]
    story: dict[str, object]
    scenes: list[Scene] = Field(min_length=25, max_length=25)
    visual_plan: VisualPlan
    audio_plan: AudioPlan
    shorts: list[Short] = Field(min_length=4, max_length=4)
    qa: QAReport = Field(default_factory=QAReport)

    def validate_contract(self) -> None:
        ids = [scene.scene_id for scene in self.scenes]
        if ids != list(range(1, 26)):
            raise ValueError("Episode must contain scene IDs 1..25 in order")
        for short in self.shorts:
            if not 28 <= short.duration <= 59:
                raise ValueError(f"Short {short.short_id} duration outside 28..59 seconds")
            if not short.scene_ids:
                raise ValueError(f"Short {short.short_id} has no source scenes")
