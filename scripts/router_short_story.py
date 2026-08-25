#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

from ai_router import AIRouter, Provider, _blockrun, _cohere, _extract
from generate_job import openrouter, gemini, cf, compat, qwencloud, normalize, PROMPT, REPAIR_PROMPT

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)


def build_router():
    providers = []
    if os.getenv("QWENCLOUD_API_KEY"):
        providers.append(Provider("QwenCloud", ["short_story"], 10, True, lambda p: qwencloud(os.environ["QWENCLOUD_API_KEY"], p), os.getenv("QWENCLOUD_MODEL", "auto-free-model")))
    if os.getenv("BLOCKRUN_FREE_ENABLED", "true").lower() == "true":
        providers.append(Provider("BlockRun", ["short_story"], 15, True, _blockrun, "blockrun-free-pool"))
    if os.getenv("GROQ_API_KEY"):
        model = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")
        providers.append(Provider("Groq", ["short_story"], 20, True, lambda p: compat("Groq", os.environ["GROQ_API_KEY"], model, p), model))
    if os.getenv("GEMINI_API_KEY"):
        providers.append(Provider("Gemini", ["short_story"], 30, True, lambda p: gemini(os.environ["GEMINI_API_KEY"], p), os.getenv("GEMINI_MODEL")))
    if os.getenv("CEREBRAS_API_KEY") and os.getenv("CEREBRAS_FREE_ONLY", "true").lower() == "true":
        from cerebras_provider import generate as cerebras_generate
        providers.append(Provider("Cerebras", ["short_story"], 35, True, lambda p: cerebras_generate(os.environ["CEREBRAS_API_KEY"], p), os.getenv("CEREBRAS_MODEL")))
    if os.getenv("COHERE_API_KEY"):
        providers.append(Provider("Cohere", ["short_story"], 40, True, lambda p: _cohere(os.environ["COHERE_API_KEY"], p), os.getenv("COHERE_MODEL", "command-r7b-12-2024")))
    if os.getenv("OPENROUTER_API_KEY"):
        model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
        providers.append(Provider("OpenRouter", ["short_story"], 70, True, lambda p: openrouter(os.environ["OPENROUTER_API_KEY"], p), model))
    if os.getenv("CLOUDFLARE_API_TOKEN") and os.getenv("CLOUDFLARE_ACCOUNT_ID"):
        providers.append(Provider("Cloudflare", ["short_story"], 75, True, lambda p: cf(os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"], p), os.getenv("CLOUDFLARE_MODEL")))
    if os.getenv("TOGETHER_API_KEY") and os.getenv("ENABLE_TOGETHER_PROVIDER", "false").lower() == "true":
        model = os.getenv("TOGETHER_TEXT_MODEL", "Qwen/Qwen3.5-9B")
        providers.append(Provider("Together", ["short_story"], 80, True, lambda p: compat("Together", os.environ["TOGETHER_API_KEY"], model, p), model))

    from compatible_provider_pool import PROVIDERS, health_check, generate
    priority = 90
    for name, cfg in PROVIDERS.items():
        if name == "Together":
            continue
        if not os.getenv(cfg["key"]):
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
    return AIRouter(providers, task="short_story")


def main():
    router = build_router()
    if not router.providers:
        raise SystemExit("Aqaaab AI Router has no eligible short-story providers")
    last = None
    excluded = set()
    schema_failures = {}
    for attempt in range(1, max(6, len(router.providers) * 2) + 1):
        prompt = PROMPT if attempt == 1 else REPAIR_PROMPT
        try:
            result, provider, model = router.route(prompt, exclude=excluded)
            d = normalize(result)
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
            print(f"Aqaaab AI Router short-story attempt {attempt} failed: {e}")
            provider = None
            try:
                ledger = json.loads((RUN_DIR / "ai_router" / "routing_ledger.json").read_text())
                passed = [x for x in ledger.get("entries", []) if x.get("decision") == "PASS"]
                if passed:
                    provider = passed[-1].get("provider")
            except Exception:
                pass
            if provider:
                msg = str(e).lower()
                is_schema = any(x in msg for x in ("scene count", "word count", "language/word", "missing fields", "unsupported absolute", "not enough tags", "weak visual_subject"))
                if is_schema:
                    schema_failures[provider] = schema_failures.get(provider, 0) + 1
                    try:
                        router.report_validation_failure(provider, e)
                    except Exception:
                        pass
                    if schema_failures[provider] >= 2:
                        excluded.add(provider)
                else:
                    excluded.add(provider)
    raise SystemExit(f"Aqaaab AI Router exhausted short-story providers: {last}")


if __name__ == "__main__":
    main()
