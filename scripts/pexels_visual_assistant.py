#!/usr/bin/env python3
from __future__ import annotations
import re
from typing import List


def _norm(text: str) -> str:
    return ' '.join(re.sub(r'[^A-Za-z0-9 -]', ' ', text.lower()).split())


def build_queries(narration: str, subject: str, role: str, scene_index: int = 0) -> List[str]:
    """Create several evidence-first Pexels queries from the scene meaning.

    The assistant deliberately searches for the visible relationship/action,
    not only the noun in visual_subject. Results are ordered from most
    semantically specific to broader fallbacks.
    """
    n = _norm(narration)
    s = _norm(subject)
    r = _norm(role)
    queries: List[str] = []

    def add(q: str):
        q = _norm(q)
        if q and q not in queries:
            queries.append(q)

    # Causal/action claims: require the visible result/context as well.
    if any(k in n for k in ('powers homes', 'power homes', 'powering homes', 'powers a home', 'home electricity', 'electricity to homes')):
        add('solar panels residential house electricity power')
        add('solar energy powering home rooftop panels')
        add('home solar electricity clean energy')
    elif any(k in n for k in ('utility bills', 'electric bill', 'electricity bill', 'lowering bills', 'save money on electricity')):
        add('solar panels house electricity savings')
        add('residential solar energy lower electricity bill')
        add('home solar panels electricity consumption')
    elif any(k in n for k in ('cutting carbon', 'carbon footprint', 'reduce emissions', 'clean energy')):
        add('solar panels home clean energy environment')
        add('renewable energy residential home emissions')
        add('clean electricity solar house')
    elif any(k in n for k in ('charges a battery', 'battery storage', 'stores energy', 'stores electricity')):
        add('solar battery home energy storage')
        add('home battery solar electricity storage')
    elif any(k in n for k in ('wind turbine', 'wind power', 'generates electricity')):
        add('wind turbine electricity power generation')
        add('wind farm renewable electricity')
    elif any(k in n for k in ('drives', 'moves', 'turns', 'spins', 'flows', 'connects', 'transfers', 'heats', 'cools')):
        add(f'{s} {r} action demonstration')
        add(f'{s} process action real world')

    # Always retain subject/context fallbacks.
    add(f'{s} {r}')
    add(f'{s} real world')
    if scene_index == 7 and any(k in n for k in ('solar', 'energy', 'homes', 'electricity')):
        add('solar panels residential home electricity')

    return queries[:5]
