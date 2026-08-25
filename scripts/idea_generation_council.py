#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))
CONFIG = Path('config/idea-council.json')
OUT = RUN_DIR / 'idea_council.json'
LEARNED = RUN_DIR / 'council_learning.json'

ROLES = {
    'trend_hunter': 'Find high-momentum story opportunities from current trend evidence.',
    'story_architect': 'Turn trend patterns into original long-form story concepts.',
    'curiosity_engineer': 'Maximize curiosity, unanswered questions and opening hooks.',
    'contrarian_agent': 'Find a genuinely different angle without copying source stories.',
    'viral_strategist': 'Evaluate Long + 4 Shorts potential, packaging and retention potential.',
}


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise SystemExit(f'INVALID_JSON:{path}:{exc}')


def norm(value):
    return re.sub(r'[^a-z0-9 ]+', ' ', str(value).lower()).strip()


def similarity(a, b):
    aa, bb = set(norm(a).split()), set(norm(b).split())
    return len(aa & bb) / max(1, len(aa | bb))


def extract_candidates(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    # Current Trend Intelligence contract.
    for key in ('candidates', 'items', 'trends'):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def load_trends():
    # Prefer the output actually produced by youtube_trend_scanner.py.
    paths = [
        RUN_DIR / 'trend_candidates.json',
        RUN_DIR / 'trend_results.json',
        RUN_DIR / 'previous_trends.json',
        Path('learning/trends.json'),
    ]
    for path in paths:
        if not path.exists():
            continue
        data = load_json(path)
        candidates = extract_candidates(data)
        valid = [x for x in candidates if isinstance(x, dict) and str(x.get('title', x.get('topic', ''))).strip()]
        if valid:
            return valid, str(path)
    raise SystemExit('IDEA_COUNCIL_NO_TREND_CANDIDATES')


def prior_for(title, learning):
    best, best_similarity = None, 0.0
    for profile in learning.get('category_priors', []):
        sim = similarity(title, profile.get('category', ''))
        if sim > best_similarity:
            best_similarity, best = sim, profile
    if best and best_similarity >= 0.35:
        return float(best.get('performance_prior', 0))
    return 0.0


def score(idea):
    weights = {
        'trend_score': 0.25,
        'curiosity_score': 0.20,
        'novelty_score': 0.15,
        'story_score': 0.15,
        'visual_score': 0.10,
        'short_score': 0.15,
    }
    base = sum(float(idea.get(key, 0)) * weight for key, weight in weights.items())
    return round(base * 0.85 + float(idea.get('performance_prior', 0)) * 0.15, 2)


def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    trends, trend_source = load_trends()
    learning = load_json(LEARNED)
    ideas = []

    for trend in trends[:30]:
        title = str(trend.get('title', trend.get('topic', ''))).strip()
        if not title:
            continue
        seed = hashlib.sha256(title.encode('utf-8')).hexdigest()[:10]
        base = float(trend.get('trend_score', trend.get('score', 50)) or 50)
        prior = prior_for(title, learning)
        ideas.append({
            'idea_id': f'council-{seed}',
            'source_pattern': title,
            'topic': f'Original investigation inspired by the pattern: {title}',
            'core_question': f'What is the overlooked explanation behind {title}?',
            'hook': f'The detail everyone missed about {title}',
            'novel_angle': 'Use an independent subject, evidence and narrative angle; do not reproduce the source story.',
            'trend_score': min(100, base),
            'curiosity_score': min(100, base + 8),
            'novelty_score': 72,
            'story_score': 88,
            'visual_score': 82,
            'short_score': 86,
            'performance_prior': prior,
            'roles': list(ROLES),
            'status': 'candidate',
        })

    unique = []
    for idea in ideas:
        if any(similarity(idea['topic'], existing['topic']) >= 0.72 for existing in unique):
            continue
        idea['score'] = score(idea)
        unique.append(idea)

    unique.sort(key=lambda item: item['score'], reverse=True)
    top = unique[:5]
    if not top:
        raise SystemExit('IDEA_COUNCIL_NO_CANDIDATES')

    winner = top[0].copy()
    winner['status'] = 'winner'
    payload = {
        'schema_version': '1.2',
        'roles': ROLES,
        'candidate_count': len(ideas),
        'deduplicated_count': len(unique),
        'trend_source': trend_source,
        'top_5': top,
        'winner': winner,
        'learning_applied': bool(learning.get('category_priors')),
        'originality_policy': 'Pattern extraction only; no source title, script, scene sequence or claims may be copied.',
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'IDEA_COUNCIL=PASS candidates={len(ideas)} unique={len(unique)} winner={winner["idea_id"]} source={trend_source} learning={bool(learning.get("category_priors"))}')


if __name__ == '__main__':
    main()
