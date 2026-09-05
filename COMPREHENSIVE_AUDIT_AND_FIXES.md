# تقرير فحص وإصلاح شامل للمشروع
## Comprehensive Project Audit & Fixes Report

**تاريخ التقرير:** 2026-09-05  
**آخر Commit:** `3d14f5be09756d6cf2eb74b7d8ecc128a395cc1d`  
**الحالة:** المشروع في مرحلة تثبيت خط الإنتاج (Production Pipeline Hardening)

---

## 📊 الملخص التنفيذي

المشروع عبارة عن نظام **إنتاج فيديوهات سيارات آلي بالكامل** يمر عبر مراحل صارمة:

```
اختيار موضوع → توليد قصة → فحص ذاتي → إخراج فيديو → فحص الجودة → نشر YouTube
```

الحالة الحالية:
- ✅ معظم المكونات موجودة وفعّالة
- ⚠️ أخطاء حرجة في التعامل مع البيانات والخطأ
- ⚠️ مسائل أمان وتسريب الب��انات الحساسة
- 🔴 متغيرات غير معرّفة قد تسبب انهيار مفاجئ

---

## 🔴 الأخطاء الحرجة (Critical Errors)

### ❌ الخطأ #1: متغير غير معرّف في `source_enrichment.py` (السطر 328)

**الملف:** `scripts/source_enrichment.py`  
**السطر:** 328  
**الخطورة:** 🔴 حرج - يسبب انهيار البرنامج

```python
# ❌ الكود الخاطئ
print(f"SOURCE_ENRICHMENT=PASS sources={len(sources)} covered_scenes={len(target_scenes)}")
```

**المشكلة:**  
`target_scenes` معرّف فقط داخل الدالة `_build_sources()` ولا يمكن الوصول إليه من الدالة `main()`. السكريبت سيتعطل عند محاولة طباعة الرسالة.

**الحل:**

```python
# ✅ الكود الصحيح
covered = len({n for source in sources for n in source["scene_numbers"]})
print(f"SOURCE_ENRICHMENT=PASS sources={len(sources)} covered_scenes={covered}")
```

---

### ❌ الخطأ #2: معالجة الأخطاء المفقودة في `renderer.py` (السطر 174)

**الملف:** `scripts/renderer.py`  
**السطر:** 174  
**الخطورة:** 🔴 حرج - قد يسبب انهيار بدون رسالة خطأ واضحة

```python
# ❌ الكود الخاطئ
probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio)], text=True)
duration = float(probe.strip())
```

**المشكلة:**  
إذا لم يكن `ffprobe` مثبتاً أو فشل في تنفيذه، سيرفع `CalledProcessError` أو `FileNotFoundError` دون معالجة.

**الحل:**

```python
# ✅ الكود الصحيح
try:
    probe = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio)],
        text=True,
        timeout=30
    )
    duration = float(probe.strip())
    if duration <= 0:
        raise RuntimeError(f"ffprobe returned invalid duration: {duration}")
except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
    raise RuntimeError(f"ffprobe failed for scene {index}: {exc}") from exc
```

---

### ❌ الخطأ #3: مسابقة حالة (Race Condition) في `youtube_upload.py` (السطور 227–231)

**الملف:** `scripts/youtube_upload.py`  
**السطور:** 227–231  
**الخطورة:** 🔴 حرج - قد يؤدي إلى رفع الفيديو برغم فشل المصادقة

```python
# ❌ الكود الخاطئ
youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
_preflight(youtube)  # قد يفشل هنا
channel = youtube.channels().list(part="id", mine=True).execute().get("items", [])  # لكن يتم تنفيذه على كل حال!
```

**المشكلة:**  
إذا فشلت `_preflight()` وأطلقت استثناء، فإن السطر 231 قد لا ينفذ. لكن البرنامج قد ينتقل إلى المرحلة التالية بقيم غير صحيحة.

**الحل:**

```python
# ✅ الكود الصحيح
youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
_preflight(youtube)  # هذا السطر قد يرفع استثناء، وهذا صحيح
response = youtube.channels().list(part="id", mine=True).execute()
channel = response.get("items", [])
if not channel:
    raise RuntimeError("YouTube OAuth succeeded but no channel is accessible")
channel_id = str(channel[0]["id"])
```

---

### ❌ الخطأ #4: تفعيل التحقق من URL مطفوء بالافتراضي في `source_enrichment.py` (السطر 19)

**الملف:** `scripts/source_enrichment.py`  
**السطر:** 19  
**الخطورة:** 🟠 عالية - يسبب عدم التحقق من صحة المصادر

```python
# ❌ الكود الخاطئ
VERIFY_REMOTE = os.getenv("SOURCE_VERIFY_REMOTE", "0") == "1"
```

**المشكلة:**  
- القيمة الافتراضية `"0"` تعني **تعطيل التحقق**
- README يدّعي "remote URL verification in production" لكنها مطفوءة فعلياً
- في معظم التشغيلات، ستُقبل المصادر **بدون التحقق من وجودها الفعلي**

**الحل:**

```python
# ✅ الكود الصحيح - تفعيل التحقق بالافتراضي
VERIFY_REMOTE = os.getenv("SOURCE_VERIFY_REMOTE", "1") == "1"
```

أو في الـ workflow (`daily-production.yml`):
```yaml
SOURCE_VERIFY_REMOTE: '1'  # التحقق مفعّل بالافتراضي
```

---

### ❌ الخطأ #5: قيم ناقصة في `story_pipeline.py` (السطر 168)

**الملف:** `scripts/story_pipeline.py`  
**السطر:** 168  
**الخطورة:** 🟠 عالية - بيانات احتياطية غير مكتملة

```python
# ❌ الكود الناقص (مقطوع في الملف)
fallback["text_ar"] = arabic_proofread(fallback.get("text_ar") or ("هذا المشهد يشرح جزءاً مهماً من موضوع السيارات ويوضح تفاصيله الفنية [...]
```

**المشكلة:**  
- النص الاحتياطي مقطوع ولم يكتمل
- لا يُمكن التأكد من أنه يستوفي متطلبات العربية (≥12 حرف عربي، ≥60% عربي)
- قد ينتج عن هذا فشل التحقق في المراحل اللاحقة

**الحل:**

```python
# ✅ الكود الصحيح والكامل
fallback_ar_text = (
    "هذا المشهد يشرح جزءاً مهماً من موضوع السيارات "
    "ويوضح تفاصيله الفنية والهندسية بشكل متدرج ومفهوم. "
    "يركز على كيفية عمل النظام وتأثيره على أداء المركبة."
)
fallback["text_ar"] = arabic_proofread(fallback.get("text_ar") or fallback_ar_text)
```

---

## 🟠 أخطاء البيانات والمنطق (Data & Logic Errors)

### ⚠️ الخطأ #6: قطع النص في `odysseus_gateway.py` (السطر 66)

**الملف:** `scripts/odysseus_gateway.py`  
**السطر:** 66  
**الخطورة:** 🟠 عالية - قد تفقد الـ headers الضرورية

```python
# ❌ الكود الناقص
req = urllib.request.Request(_url(base), data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accep[...]
```

**المشكلة:**  
- رأس `Accept` مقطوع
- قد تكون هناك رؤوس أخرى ناقصة مهمة للاتصال

**الحل:**

```python
# ✅ الكود الصحيح والكامل
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "faceless-youtube-shorts-n8n/2.1"
}
req = urllib.request.Request(_url(base), data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
```

---

### ⚠️ الخطأ #7: إزالة نسخة من المصادر في `source_enrichment.py` (السطور 156–166)

**الملف:** `scripts/source_enrichment.py`  
**الدالة:** `_dedupe()`  
**الخطورة:** 🟡 متوسطة - قد يفقد بعض المصادر

```python
# الكود الحالي (يعمل لكن ضعيف)
def _dedupe(sources: list[dict]) -> list[dict]:
    result, seen = [], set()
    for source in sources:
        key = source["url"].rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        # ...
```

**المشاكل:**
1. **فقط معايرة عنوان URL** - مصدران بنفس الادعاء لكن URLs مختلفة لن يُدمجا
2. **معاملات Query لا تُعامل بشكل موحد** - `?ref=1` و `?ref=2` يُعتبران مختلفان

**الحل:**

```python
# ✅ الكود المحسّن
from urllib.parse import urlparse, parse_qs

def _normalize_url(url: str) -> str:
    """Normalize URL for comparison: remove fragment, sort query params."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    # إعادة بناء URL بمعايير موحدة
    sorted_params = "&".join(
        f"{k}={','.join(sorted(v))}" for k, v in sorted(params.items())
    )
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if sorted_params:
        normalized += f"?{sorted_params}"
    return normalized

def _dedupe(sources: list[dict]) -> list[dict]:
    result, seen = [], set()
    for source in sources:
        normalized_url = _normalize_url(source["url"])
        # استخدام (URL + Claim) كمفتاح فريد
        key = (normalized_url, source.get("claim", "").strip()[:100].casefold())
        if key in seen:
            continue
        seen.add(key)
        source["id"] = source.get("id") or f"src-{len(result) + 1:02d}"
        result.append(source)
    return result
```

---

## 🔒 مشاكل الأمان (Security Issues)

### 🔴 الخطأ #8: تسريب مفاتيح API في رسائل الخطأ

**الملفات المتأثرة:**
- `scripts/odysseus_gateway.py` (السطر 75)
- `scripts/youtube_upload.py` (السطور 125, 191)
- `scripts/source_enrichment.py` (السطر 273)

**المشكلة:**
```python
# ❌ خطر! قد تطبع رسالة خطأ تحتوي على API key
detail = exc.read().decode("utf-8", "replace")[:1000]
last_error = RuntimeError(f"Odysseus HTTP {exc.code}: {detail}")
```

إذا أرجعت الخدمة رسالة خطأ تحتوي على المفتاح (كما يحدث في بعض الخدمات)، سيُطبع المفتاح في السجلات.

**الحل:**

```python
# ✅ تنظيف الرسالة من البيانات الحساسة
def _sanitize_error(detail: str, api_key: str | None = None) -> str:
    """Remove API keys and tokens from error messages."""
    sanitized = str(detail)
    if api_key:
        sanitized = sanitized.replace(api_key, "***REDACTED***")
    # إزالة patterns شائعة
    sanitized = re.sub(r'["\']?Authorization["\']?\s*[:=]\s*["\']?[^"\']*["\']?', 'Authorization: ***REDACTED***', sanitized)
    sanitized = re.sub(r'["\']?key["\']?\s*[:=]\s*["\']?[^"\']*["\']?', 'key: ***REDACTED***', sanitized)
    sanitized = re.sub(r'["\']?token["\']?\s*[:=]\s*["\']?[^"\']*["\']?', 'token: ***REDACTED***', sanitized)
    return sanitized[:500]

# الاستخدام:
try:
    # ... code ...
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", "replace")
    safe_detail = _sanitize_error(detail, api_key)
    last_error = RuntimeError(f"Odysseus HTTP {exc.code}: {safe_detail}")
```

---

## ⚙️ مشاكل الأداء والموارد

### ⚠️ الخطأ #9: فترات الانتظار الطويلة في `renderer.py` (السطر 44)

**الملف:** `scripts/renderer.py`  
**الخطورة:** 🟡 متوسطة - يبطّئ الإنتاج

```python
# الكود الحالي
time.sleep(min(8, 2**attempt))
```

**المشكلة:**  
مع 3 مرات إعادة محاولة لكل من 25 مشهد:
- محاولة 1: sleep 1s
- محاولة 2: sleep 2s
- محاولة 3: sleep 4s
- محاولة 4: sleep 8s

**المجموع:** 25 مشهد × 15 ثانية = **375 ثانية (6+ دقائق) من الانتظار فقط!**

**الحل:**

```python
# ✅ إعادة محاولة أذكى مع cap أقل
def shell_retry(*cmd: str, timeout: int = CMD_TIMEOUT, retries: int | None = None) -> None:
    attempts = max(1, retries if retries is not None else RETRIES)
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            shell(*cmd, timeout=timeout)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            last = exc
            if attempt + 1 < attempts:
                # أقصر وأذكى: 0.5s, 1s, 2s بدلاً من 1s, 2s, 4s, 8s
                delay = min(4, 0.5 * (2 ** attempt))
                time.sleep(delay)
    raise RuntimeError(f"command failed after {attempts} attempts: {' '.join(cmd)}") from last
```

---

## 📋 جدول الإصلاحات المطلوبة

| # | الملف | السطر | الخطورة | النوع | الحل |
|---|------|--------|---------|--------|-----|
| 1 | source_enrichment.py | 328 | 🔴 حرج | متغير غير معرّف | تعريف المتغير محلياً |
| 2 | renderer.py | 174 | 🔴 حرج | معالجة أخطاء | إضافة try-except |
| 3 | youtube_upload.py | 227-231 | 🔴 حرج | مسابقة حالة | إعادة هيكلة التحكم بالتدفق |
| 4 | source_enrichment.py | 19 | 🟠 عالية | إعدادات | تفعيل التحقق بالافتراضي |
| 5 | story_pipeline.py | 168 | 🟠 عالية | بيانات ناقصة | إكمال النص الاحتياطي |
| 6 | odysseus_gateway.py | 66 | 🟠 عالية | رؤوس ناقصة | إكمال رؤوس الطلب |
| 7 | source_enrichment.py | 156 | 🟡 متوسطة | منطق ضعيف | تحسين إزالة التكرار |
| 8 | متعدد | متعدد | 🔴 حرج | أمان | تنظيف رسائل الخطأ |
| 9 | renderer.py | 44 | 🟡 متوسطة | أداء | تقليل فترات الانتظار |

---

## ✅ خطة الإصلاح الفوري (Immediate Action Plan)

### المرحلة 1: الإصلاحات الحرجة (Critical - اليوم)

```bash
# 1. إصلاح source_enrichment.py
# 2. إصلاح renderer.py
# 3. إصلاح youtube_upload.py
# 4. اختبار محلي للتحقق من عدم وجود أخطاء واضحة
```

### المرحلة 2: الإصلاحات العالية (High Priority - غداً)

```bash
# 1. تفعيل SOURCE_VERIFY_REMOTE بالافتراضي
# 2. إكمال النصوص الناقصة
# 3. إكمال رؤوس الطلبات
# 4. اختبار مع بيانات حقيقية
```

### المرحلة 3: التحسينات (Improvements - هذا الأسبوع)

```bash
# 1. تحسين إزالة التكرار
# 2. تنظيف رسائل الخطأ من البيانات الحساسة
# 3. تحسين الأداء بإعادة المحاولات الأذكى
# 4. إضافة اختبارات شاملة
```

---

## 🧪 خطة الاختبار (Testing Strategy)

### 1. اختبارات الوحدة (Unit Tests)

```python
# tests/test_source_enrichment.py
def test_main_no_undefined_variables():
    """Ensure all variables are defined before use."""
    # ...

# tests/test_renderer.py
def test_ffprobe_error_handling():
    """Verify ffprobe errors are caught properly."""
    # ...

# tests/test_youtube_upload.py
def test_oauth_preflight_required():
    """Verify preflight must pass before proceeding."""
    # ...
```

### 2. اختبارات التكامل (Integration Tests)

```bash
# اختبار الخط كاملاً بدون رفع فعلي
python scripts/select_car_topic.py
python scripts/story_pipeline.py
python scripts/renderer.py --dry-run
```

### 3. اختبارات الأمان (Security Tests)

```bash
# البحث عن تسريب مفاتيح محتملة
grep -r "ODYSSEUS\|API_KEY\|SECRET\|TOKEN" scripts/*.py | grep -v "os.getenv"
```

---

## 📚 قائمة المراجعة النهائية (Final Checklist)

- [ ] تصحيح جميع متغيرات المتغيرات غير المعرّفة
- [ ] إضافة معالجة شاملة للأخطاء
- [ ] تنظيف رسائل الخطأ من البيانات الحساسة
- [ ] تفعيل التحقق من المصادر بالافتراضي
- [ ] إكمال جميع النصوص والرؤوس الناقصة
- [ ] تشغيل جميع الاختبارات المحلية
- [ ] التحقق من عدم وجود أخطاء في السجلات
- [ ] اختبار الخط كاملاً بدون رفع فعلي
- [ ] مراجعة القيمة الحساسة في الـ secrets
- [ ] توثيق أي تغييرات في قاعدة الكود

---

## 🚀 الخطوات التالية

1. **تطبيق الإصلاحات من المرحلة 1** (Critical)
2. **اختبار محلي سريع** (15 دقيقة)
3. **تطبيق الإصلاحات من المرحلة 2** (High Priority)
4. **تشغيل الخط الكامل في بيئة الاختبار**
5. **مراجعة السجلات والقطع الفنية (Artifacts)**
6. **نشر التغييرات للإنتاج**

---

**ملاحظة نهائية:**  
هذا التقرير يعالج **الأخطاء الفعلية والمحتملة**. التطبيق الكامل للإصلاحات سيضمن استقرار النظام وموثوقيته.

