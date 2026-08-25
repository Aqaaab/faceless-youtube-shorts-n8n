#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

from ai_router import AIRouter, Provider, _blockrun, _cohere, _extract
from generate_job import openrouter, gemini, cf, compat, qwencloud, normalize

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

STRICT_PROMPT = '''Create ONE factual, high-retention YouTube Shorts story in English. Return ONLY one JSON object, no markdown.
Use EXACTLY 6 scenes. Every scene MUST contain text_en, text_ar, visual_subject, pexels_query.
Each text_en scene MUST contain 8-18 English words; target 12-15. Total English narration MUST be 80-110 words.
text_en must contain only English/ASCII letters and normal punctuation; NEVER Arabic characters.
text_ar must be a faithful Modern Standard Arabic translation of the corresponding text_en.
visual_subject must be 1-3 concrete physical words. pexels_query must be 2-5 concrete English words and include the core subject.
No CTA, no absolute claims, no unsupported superlatives. Keep the topic factual and internally consistent.
script is all text_en scenes joined by spaces; narration equals script; subtitle_ar is all text_ar scenes joined by spaces.
Title: English-only, <=85 characters, ending exactly with #Shorts. Description: 2-3 factual English sentences followed by exactly 5 relevant hashtags. Tags: 8-12 lowercase ASCII tokens.'''


def repair_prompt(error: str, previous: object | None) -> str:
    previous_json = json.dumps(previous, ensure_ascii=False, indent=2) if isinstance(previous, dict) else "(no previous JSON available)"
    return f'''REPAIR THE PREVIOUS YouTube Shorts JSON. Return ONLY one complete JSON object, no markdown.
The previous result failed this validator: {error}
Keep the same factual topic and preserve valid content. Fix the failure directly; do not merely explain it.
Use EXACTLY 6 scenes. Every scene MUST contain text_en, text_ar, visual_subject, pexels_query.
Each text_en MUST contain 8-18 English words; target 12-15. Total English narration MUST be 80-110 words.
text_en must contain only English/ASCII letters and normal punctuation; NEVER Arabic characters.
text_ar must be faithful Modern Standard Arabic. visual_subject must be 1-3 concrete physical words. pexels_query must be 2-5 concrete English words containing the core subject.
No CTA, absolute claims, or unsupported superlatives.
Include topic, category, English title <=85 characters ending #Shorts, 2-3 factual English description sentences followed by exactly 5 hashtags, and 8-12 lowercase ASCII tags.

PREVIOUS JSON TO REPAIR:
{previous_json}'''


def build_router():
    providers = []
    from compatible_provider_pool import PROVIDERS, health_check, generate
    priority = 10
    for name in ("Mistral", "HuggingFace", "SambaNova", "LLM7", "ArliAI", "OllamaCloud"):
        cfg = PROVIDERS.get(name)
        if not cfg or not os.getenv(cfg["key"]):
            continue
        if os.getenv(f"ENABLE_{name.upper()}_PROVIDER", "false").lower() != "true":
            continue
        ok, reason = health_check(name)
        if not ok:
            print(f"PROVIDER_HEALTH_SKIP provider={name} reason={reason}")
            continue
        model = os.getenv(f"{name.upper()}_MODEL", cfg["model"])
        providers.append(Provider(name, ["short_story"], priority, True, lambda p, n=name: _extract(generate(n, p)["content"]), model))
        print(f"PROVIDER_HEALTH_PASS provider={name}")
        priority += 1

    if os.getenv("QWENCLOUD_API_KEY"):
        providers.append(Provider("QwenCloud", ["short_story"], 30, True, lambda p: qwencloud(os.environ["QWENCLOUD_API_KEY"], p), os.getenv("QWENCLOUD_MODEL", "auto-free-model")))
    if os.getenv("BLOCKRUN_FREE_ENABLED", "true").lower() == "true":
        providers.append(Provider("BlockRun", ["short_story"], 35, True, _blockrun, "blockrun-free-pool"))
    if os.getenv("GROQ_API_KEY"):
        model = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")
        providers.append(Provider("Groq", ["short_story"], 40, True, lambda p: compat("Groq", os.environ["GROQ_API_KEY"], model, p), model))
    if os.getenv("GEMINI_API_KEY"):
        providers.append(Provider("Gemini", ["short_story"], 50, True, lambda p: gemini(os.environ["GEMINI_API_KEY"], p), os.getenv("GEMINI_MODEL")))
    if os.getenv("CEREBRAS_API_KEY") and os.getenv("CEREBRAS_FREE_ONLY", "true").lower() == "true":
        from cerebras_provider import generate as cerebras_generate
        providers.append(Provider("Cerebras", ["short_story"], 55, True, lambda p: cerebras_generate(os.environ["CEREBRAS_API_KEY"], p), os.getenv("CEREBRAS_MODEL")))
    if os.getenv("COHERE_API_KEY"):
        providers.append(Provider("Cohere", ["short_story"], 60, True, lambda p: _cohere(os.environ["COHERE_API_KEY"], p), os.getenv("COHERE_MODEL", "command-r7b-12-2024")))
    if os.getenv("OPENROUTER_API_KEY"):
        model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
        providers.append(Provider("OpenRouter", ["short_story"], 70, True, lambda p: openrouter(os.environ["OPENROUTER_API_KEY"], p), model))
    if os.getenv("CLOUDFLARE_API_TOKEN") and os.getenv("CLOUDFLARE_ACCOUNT_ID"):
        providers.append(Provider("Cloudflare", ["short_story"], 75, True, lambda p: cf(os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"], p), os.getenv("CLOUDFLARE_MODEL")))
    if os.getenv("TOGETHER_API_KEY") and os.getenv("ENABLE_TOGETHER_PROVIDER", "false").lower() == "true":
        model = os.getenv("TOGETHER_TEXT_MODEL", "Qwen/Qwen3.5-9B")
        providers.append(Provider("Together", ["short_story"], 80, True, lambda p: compat("Together", os.environ["TOGETHER_API_KEY"], model, p), model))
    return AIRouter(providers, task="short_story")


def _validation_provider(router: AIRouter, run_dir: Path) -> str | None:
    try:
        ledger = json.loads((run_dir / "ai_router" / "routing_ledger.json").read_text())
        passed = [x for x in ledger.get("entries", []) if x.get("decision") == "PASS"]
        if passed:
            return passed[-1].get("provider")
    except Exception:
        pass
    return None


def main():
    router = build_router()
    if not router.providers:
        raise SystemExit("Aqaaab AI Router has no eligible short-story providers")

    excluded: set[str] = set()
    schema_failures: dict[str, int] = {}
    current_error = "initial generation"
    previous: object | None = None
    last = None
    max_attempts = max(18, len(router.providers) * 4)

    for attempt in range(1, max_attempts + 1):
        prompt = STRICT_PROMPT if previous is None else repair_prompt(current_error, previous)
        try:
            result, provider, model = router.route(prompt, exclude=excluded)
            previous = result
            try:
                d = normalize(result)
            except Exception as validation_error:
                current_error = str(validation_error)
                last = validation_error
                schema_failures[provider] = schema_failures.get(provider, 0) + 1
                try:
                    router.report_validation_failure(provider, validation_error)
                except Exception:
                    pass
                if schema_failures[provider] >= 4:
                    excluded.add(provider)
                print(f"Aqaaab AI Router schema repair provider={provider} failure={schema_failures[provider]} error={validation_error}")
                continue

            d["provider"] = provider
            d["model"] = model
            d["router"] = "Aqaaab AI Router"
            d["router_task"] = "short_story"
            d["generation_attempt"] = attempt
            (RUN_DIR / "job.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"SHORT_STORY router=Aqaaab-AI-Router provider={provider} model={model} scenes={d['scene_count']} words={len(d['script'].split())} attempt={attempt}")
            return
        except Exception as e:
            last = e
            current_error = str(e)
            print(f"Aqaaab AI Router short-story attempt {attempt} failed: {e}")
            provider = _validation_provider(router, RUN_DIR)
            msg = current_error.lower()
            is_schema = any(x in msg for x in ("scene count", "word count", "language/word", "missing fields", "unsupported absolute", "not enough tags", "weak visual_subject", "visual/query length contract"))
            if provider:
                if is_schema:
                    schema_failures[provider] = schema_failures.get(provider, 0) + 1
                    try:
                        router.report_validation_failure(provider, e)
                    except Exception:
                        pass
                    if schema_failures[provider] >= 4:
                        excluded.add(provider)
                else:
                    excluded.add(provider)
                    previous = None

    raise SystemExit(f"Aqaaab AI Router exhausted short-story providers: {last}")


if __name__ == "__main__":
    main()
