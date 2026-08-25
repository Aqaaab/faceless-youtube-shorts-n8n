#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path

RUN = Path(os.environ.get('RUN_DIR', 'data/run'))
LEARNING = Path(os.environ.get('LEARNING_DIR', 'learning'))
OUT = RUN / 'council_learning.json'


def load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'WARN learning file invalid: {path}: {exc}')
        return {}


def main():
    LEARNING.mkdir(parents=True, exist_ok=True)
    RUN.mkdir(parents=True, exist_ok=True)
    sources = [
        LEARNING / 'performance.json',
        LEARNING / 'youtube_performance.json',
        RUN / 'performance.json',
        LEARNING / 'metrics.json',
    ]
    records = []
    for path in sources:
        data = load(path)
        if not isinstance(data, dict):
            continue
        value = data.get('records', data.get('items', []))
        if isinstance(value, list):
            records.extend(x for x in value if isinstance(x, dict))

    profiles = {}
    for record in records:
        category = str(record.get('category', record.get('topic', 'unknown'))).lower().strip() or 'unknown'
        profile = profiles.setdefault(category, {'n': 0, 'ctr': [], 'retention': [], 'avd': [], 'velocity': [], 'shorts': []})
        profile['n'] += 1
        aliases = {
            'ctr': ['ctr', 'click_through_rate'],
            'retention': ['retention', 'avg_retention'],
            'avd': ['avd', 'average_view_duration'],
            'velocity': ['views_velocity', 'velocity'],
            'shorts': ['shorts_score', 'short_performance'],
        }
        for key, names in aliases.items():
            for name in names:
                if record.get(name) is None:
                    continue
                try:
                    profile[key].append(float(record[name]))
                except (TypeError, ValueError):
                    pass
                break

    def avg(values):
        return round(sum(values) / len(values), 3) if values else None

    for profile in profiles.values():
        for key in ('ctr', 'retention', 'avd', 'velocity', 'shorts'):
            profile[key] = avg(profile[key])

    priors = []
    for category, profile in profiles.items():
        values = [v for v in (profile['ctr'], profile['retention'], profile['velocity'], profile['shorts']) if v is not None]
        priors.append({
            'category': category,
            'sample_size': profile['n'],
            'performance_prior': round(sum(values) / len(values), 3) if values else 0,
            'metrics': profile,
        })
    priors.sort(key=lambda item: item['performance_prior'], reverse=True)

    payload = {
        'schema_version': '1.1',
        'records_seen': len(records),
        'category_priors': priors,
        'learning_available': bool(priors),
        'usage': 'Use as a bounded prior for council scoring; never replace fresh trend evidence.',
        'source_files': [str(path) for path in sources if path.exists()],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'COUNCIL_LEARNING=PASS records={len(records)} categories={len(priors)} available={bool(priors)}')


if __name__ == '__main__':
    main()
