from app.render import _subtitle_text


def test_subtitle_wrapper_keeps_every_line_within_gate_limit():
    text = (
        "السيارة الجديدة تجمع بين تصميم عملي وتقنيات حديثة وأداء متوازن يمنح السائق تجربة واضحة "
        "ومتماسكة في الاستخدام اليومي مع تركيز على التفاصيل الهندسية التي تميز هذا الطراز ضمن فئته "
        "وتساعد على فهم نقاط القوة الأساسية دون مبالغة أو ادعاءات غير مثبتة"
    )
    rendered = _subtitle_text(text, 42)
    lines = rendered.split("\\N")
    assert len(lines) >= 3
    assert all(len(line) <= 42 for line in lines)
    assert " ".join(lines).split() == text.split()


def test_subtitle_wrapper_splits_pathological_long_token():
    rendered = _subtitle_text("كلمة" + "ا" * 100, 42)
    assert all(len(line) <= 42 for line in rendered.split("\\N"))
