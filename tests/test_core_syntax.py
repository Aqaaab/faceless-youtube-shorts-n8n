from pathlib import Path


def test_core_source_compiles():
    source = Path('app/core.py').read_text(encoding='utf-8')
    compile(source, 'app/core.py', 'exec')
