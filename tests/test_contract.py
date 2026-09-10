from pathlib import Path
ROOT=Path(__file__).parents[1]

def test_source_is_clean():
    tokens=['pex'+'els','render_'+'manifest.json','generated_'+'still_first','stock-'+'video']
    for p in ROOT.rglob('*'):
        if not p.is_file() or '.git' in p.parts: continue
        if p.suffix in {'.py','.yml','.yaml','.md','.json','.txt'}:
            text=p.read_text(encoding='utf-8',errors='ignore').lower()
            for token in tokens: assert token not in text, f'forbidden legacy token in {p}'

def test_contract_constants():
    t=(ROOT/'app'/'qa.py').read_text()
    assert 'len(story.scenes)!=25' in t
    assert '1080,1920' in t
    assert '28<=d<=59' in t
