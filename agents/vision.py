"""Real video understanding for the Skill Assessment agent.

The uploaded video is sent to Google Gemini, which watches it directly (no
frame extraction / ffmpeg needed) and dynamically discovers the work shown:

* the **profession / work category** the activity belongs to (not chosen by the
  worker and not restricted to a fixed list),
* the individual **skills demonstrated**, each with its own score, level,
  confidence, reason, strengths, improvements, recommendations and the visual
  evidence / timestamps behind the rating,
* how strong the evidence is for every skill
  (``observed`` / ``partial`` / ``claimed`` / ``insufficient``) so the app can
  refuse to fabricate a rating,
* an **audio / speech analysis** — the worker's spoken words are transcribed
  and checked against the work actually shown.

The call is made with the standard library only (``urllib``), so no extra
package is required. When ``KAAMSETU_GEMINI_API_KEY`` is not set, ``analyze()``
returns ``None`` and the caller falls back to the rule-based report — the app
keeps working without any key.
"""
import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request

from django.conf import settings

from agents.logic import log_agent

API_ROOT = 'https://generativelanguage.googleapis.com'
# Gemini accepts inline video up to ~20 MB; anything larger goes through the
# File API (upload -> wait until ACTIVE -> reference by URI).
INLINE_LIMIT = 15 * 1024 * 1024
POLL_SECONDS = 3
POLL_ATTEMPTS = 40
# Dynamic discovery levels (task vocabulary). The profile still uses the
# 3-level beginner/working/skilled scheme and maps onto it when a skill is
# accepted — see ``workers.models.DetectedSkill.PROFILE_LEVEL``.
LEVELS = ('beginner', 'intermediate', 'advanced', 'expert')
LEVEL_ALIASES = {
    'beginner': 'beginner', 'basic': 'beginner', 'novice': 'beginner', 'starter': 'beginner',
    'working': 'intermediate', 'intermediate': 'intermediate', 'mid': 'intermediate',
    'skilled': 'advanced', 'advanced': 'advanced', 'proficient': 'advanced',
    'expert': 'expert', 'professional': 'expert', 'master': 'expert',
}
# How strong the evidence behind a skill rating is.
EVIDENCE = ('observed', 'partial', 'claimed', 'insufficient')
EVIDENCE_ALIASES = {
    'observed and assessable': 'observed', 'fully observed': 'observed',
    'observed': 'observed', 'assessable': 'observed', 'demonstrated': 'observed',
    'partially observed': 'partial', 'partial': 'partial', 'partly observed': 'partial',
    'claimed but not demonstrated': 'claimed', 'not demonstrated': 'claimed',
    'claimed': 'claimed', 'mentioned': 'claimed', 'stated': 'claimed', 'verbal': 'claimed',
    'insufficient evidence': 'insufficient', 'insufficient': 'insufficient',
    'not visible': 'insufficient', 'cannot be judged': 'insufficient',
    'unclear': 'insufficient', 'unknown': 'insufficient',
}
# Cap on how many discovered skills we keep from one video.
MAX_SKILLS = 8
# Gemini free-tier models get overloaded (503) or drop connections now and then.
# If the configured model fails, these are tried in order before giving up.
FALLBACK_MODELS = ('gemini-3.5-flash-lite', 'gemini-3.1-flash-lite')
RETRY_ATTEMPTS = 2
RETRY_PAUSE = 1.5


def _config():
    cfg = getattr(settings, 'KAAMSETU', {})
    key = str(cfg.get('GEMINI_API_KEY') or '').strip()
    model = str(cfg.get('GEMINI_MODEL') or '').strip() or 'gemini-3-flash-preview'
    return key, model


def is_enabled():
    """True when a Gemini API key is configured."""
    return bool(_config()[0])


def analyze(video_file, allowed_skills=()):
    """Watch ``video_file`` and return the discovered work, or ``None``.

    Returned shape::

        {'provider': 'gemini', 'model': 'gemini-2.5-flash',
         'profession': 'Cooking', 'profession_confidence': 0.9,
         'work_summary': '...', 'overall_summary': '...',
         'skills': [
            {'name': 'Knife Handling', 'description': '...', 'category': 'Cooking',
             'score': 78, 'level': 'intermediate', 'confidence': 0.8,
             'reason': '...', 'strengths': [...], 'improvements': [...],
             'recommendations': [...], 'evidence': ['00:12 slicing onions evenly'],
             'limitations': '', 'evidence_status': 'observed'},
            ...
         ],
         'insufficient_notes': [...],
         'has_speech': True, 'transcript': '...', 'speech_language': 'Hindi',
         'speech_quality': 'clear', 'speech_correct': True,
         'speech_feedback': '...'}

    ``allowed_skills`` is only a naming hint for the model — it never restricts
    discovery. Returns ``None`` when there is no key or the call failed.
    """
    key, model = _config()
    if not key:
        return None
    try:
        return _analyze(video_file, allowed_skills, key, model)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        log_agent(
            'SkillVisionAgent', 'worker', '',
            f'Vision analysis failed: {exc.__class__.__name__}: {exc}',
        )
        return None


def _analyze(video_file, allowed_skills, key, model):
    name = getattr(video_file, 'name', '') or 'video.mp4'
    mime = mimetypes.guess_type(name)[0] or 'video/mp4'
    video_file.seek(0)
    data = video_file.read()
    video_file.seek(0)
    if not data:
        return None

    if len(data) <= INLINE_LIMIT:
        part = {'inline_data': {'mime_type': mime, 'data': base64.b64encode(data).decode()}}
    else:
        uri = _upload(data, mime, key)
        if not uri:
            return None
        part = {'file_data': {'mime_type': mime, 'file_uri': uri}}

    answer, used_model = _generate(part, allowed_skills, key, model)
    if not answer:
        return None

    skills = _normalize_skills(answer.get('skills'))
    profession = str(answer.get('profession') or '').strip()[:80]
    if not skills and not profession:
        return None

    result = {
        'provider': 'gemini',
        'model': used_model,
        'profession': profession,
        'profession_confidence': _clamp01(answer.get('profession_confidence'), 0.7),
        'work_summary': str(answer.get('work_summary') or '').strip()[:400],
        'overall_summary': str(answer.get('overall_summary') or '').strip()[:400],
        'skills': skills,
        'insufficient_notes': _as_list(answer.get('insufficient_notes'), limit=6),
        **_speech(answer),
    }
    speech_note = (
        f', speech {result["speech_quality"]}'
        if result['has_speech'] else ', no speech'
    )
    log_agent(
        'SkillVisionAgent', 'worker', '',
        f'{used_model} watched "{name}" -> {profession or "unknown profession"}: '
        f'{len(skills)} skill(s) found{speech_note}',
        result,
    )
    return result


def _generate(part, allowed_skills, key, model):
    """Ask Gemini to watch the clip, with retries and model fallback.

    Free-tier models intermittently answer ``503`` (overloaded) or drop the
    connection. Each model is retried ``RETRY_ATTEMPTS`` times; if it still
    fails, the next model in ``FALLBACK_MODELS`` is tried. Returns
    ``(answer, model_used)`` — ``({}, '')`` when every model gave up.
    """
    payload = {
        'contents': [{'parts': [{'text': _prompt(allowed_skills)}, part]}],
        'generationConfig': {'temperature': 0.2, 'responseMimeType': 'application/json'},
    }
    models = [model] + [name for name in FALLBACK_MODELS if name != model]
    last_error = None
    for name in models:
        url = f'{API_ROOT}/v1beta/models/{name}:generateContent?key={key}'
        for attempt in range(RETRY_ATTEMPTS):
            try:
                answer = _parse_json(_first_text(_post_json(url, payload)))
            except urllib.error.HTTPError as exc:
                last_error = exc
                # 404 -> model not available for this key; try the next model.
                if exc.code == 404:
                    break
                time.sleep(RETRY_PAUSE)
                continue
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
                time.sleep(RETRY_PAUSE)
                continue
            if answer.get('skills') or answer.get('profession'):
                return answer, name
            break
    if last_error is not None:
        raise last_error
    return {}, ''


def _speech(answer):
    """Build the audio/speech block from the model's reply."""
    transcript = str(answer.get('transcript') or '').strip()[:600]
    has_speech = _as_bool(answer.get('has_speech'))
    if not has_speech and transcript:
        has_speech = True
    if not has_speech:
        return {
            'has_speech': False,
            'transcript': '',
            'speech_language': '',
            'speech_quality': 'none',
            'speech_correct': None,
            'speech_feedback': '',
        }
    quality = str(answer.get('speech_quality') or '').strip().lower()
    if quality not in ('clear', 'unclear'):
        quality = 'clear'
    return {
        'has_speech': True,
        'transcript': transcript,
        'speech_language': str(answer.get('speech_language') or '').strip()[:60],
        'speech_quality': quality,
        'speech_correct': _as_bool(answer.get('speech_correct')),
        'speech_feedback': str(answer.get('speech_feedback') or '').strip()[:300],
    }


def _as_bool(value):
    """Tolerant ``True`` / ``False`` / ``None`` parsing."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ('true', 'yes', '1'):
            return True
        if low in ('false', 'no', '0'):
            return False
    return None


def _as_list(value, limit=8):
    """Normalise a comma separated string or list into a clean list."""
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, (list, tuple)):
        return []
    items = []
    for raw in value:
        text = str(raw or '').strip()[:80]
        if text:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _prompt(allowed_skills):
    skills = ', '.join(sorted({str(s).strip() for s in allowed_skills if str(s).strip()}))
    return (
        'You are the skill-discovery agent for KaamSetu, a job platform for rural '
        'workers in India. Watch AND listen to this short video in which a worker '
        'demonstrates real work and may speak.\n'
        'Discover the work dynamically from what you actually SEE and HEAR. Do not rely '
        'on the file name or on any skill the worker may have pre-selected.\n'
        f'Known platform skills (optional naming reference ONLY — do not let this list '
        f'limit or restrict your discovery): {skills or "none"}.\n'
        '\n'
        'Rules:\n'
        '- Only rate work you can actually observe happening in the video.\n'
        '- Never give a high score just because the worker looks confident or claims experience.\n'
        '- If a skill is only spoken about but not shown, set evidence_status "claimed" and give no score.\n'
        '- If the video is too short, unclear or incomplete for a skill, set evidence_status '
        '"insufficient" and give no score.\n'
        '- Use "partial" when only part of the skill is visible.\n'
        '- Do not invent hidden qualities (food taste, durability, unseen safety, certification).\n'
        '\n'
        'Return a SINGLE JSON object with exactly these keys:\n'
        '{\n'
        '  "profession": "short English profession name, e.g. Cooking / Bike repair / Tailoring",\n'
        '  "profession_confidence": 0.0,\n'
        '  "work_summary": "1-2 English sentences describing what the worker is doing",\n'
        '  "skills": [\n'
        '    {"name": "short skill name (max 3 words)",\n'
        '     "description": "one sentence",\n'
        '     "category": "profession/category this belongs to",\n'
        '     "score": 0,\n'
        '     "level": "beginner" | "intermediate" | "advanced" | "expert",\n'
        '     "confidence": 0.0,\n'
        '     "reason": "why this score, based on what you saw (max 25 words)",\n'
        '     "strengths": ["observable strength"],\n'
        '     "improvements": ["observable area to improve"],\n'
        '     "recommendations": ["specific, actionable advice"],\n'
        '     "evidence": ["mm:ss what you saw", "..."],\n'
        '     "limitations": "what could not be judged, or empty string",\n'
        '     "evidence_status": "observed" | "partial" | "claimed" | "insufficient"}\n'
        '  ],\n'
        '  "insufficient_notes": ["skills or aspects with not enough evidence"],\n'
        '  "overall_summary": "2-3 English sentences summarising the assessment",\n'
        '  "has_speech": false,\n'
        '  "transcript": "English translation of what the worker said (max 60 words), empty if none",\n'
        '  "speech_language": "e.g. Hindi, or empty",\n'
        '  "speech_quality": "clear" | "unclear" | "none",\n'
        '  "speech_correct": true | false | null,\n'
        '  "speech_feedback": "one English sentence of feedback on the spoken explanation, empty if none"\n'
        '}\n'
        f'Discover every genuinely different skill the video shows (typically 2-6, max {MAX_SKILLS}). '
        'Set "score" to null (and level to "") for any skill with claimed or insufficient evidence. '
        'Reply with JSON only.'
    )


def _normalize_skills(value, limit=MAX_SKILLS):
    """Validate and clean the model's ``skills`` list."""
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for raw in value:
        skill = _normalize_skill(raw)
        if skill:
            out.append(skill)
        if len(out) >= limit:
            break
    return out


def _normalize_skill(raw):
    """Normalise one detected skill into a safe, template-friendly dict.

    Malformed entries are dropped and, crucially, no score is invented when the
    evidence is only claimed or insufficient.
    """
    if not isinstance(raw, dict):
        return None
    name = str(raw.get('name') or raw.get('skill') or '').strip()[:80]
    if not name:
        return None

    status = _norm_evidence(raw.get('evidence_status') or raw.get('evidence'))
    level = _norm_level(raw.get('level'))
    score = _int_score(raw.get('score'))
    if status not in EVIDENCE:
        status = 'observed' if score is not None else 'insufficient'
    if status in ('claimed', 'insufficient'):
        # Claimed / unseen work must never carry a fabricated rating.
        score, level = None, ''
    elif score is None:
        status = 'partial' if level else 'insufficient'
    if score is not None:
        level = level or _score_level(score)

    return {
        'name': name,
        'description': str(raw.get('description') or '').strip()[:300],
        'category': str(raw.get('category') or '').strip()[:80],
        'score': score,
        'level': level,
        'confidence': _clamp01(raw.get('confidence'), 0.6),
        'reason': str(raw.get('reason') or '').strip()[:400],
        'strengths': _as_list(raw.get('strengths'), limit=6),
        'improvements': _as_list(raw.get('improvements'), limit=6),
        'recommendations': _as_list(raw.get('recommendations'), limit=6),
        'evidence': _as_list(raw.get('evidence'), limit=6),
        'limitations': str(raw.get('limitations') or '').strip()[:300],
        'evidence_status': status,
    }


def _score_level(score):
    if score >= 85:
        return 'expert'
    if score >= 70:
        return 'advanced'
    if score >= 50:
        return 'intermediate'
    return 'beginner'


def _norm_level(value):
    low = str(value or '').strip().lower()
    return LEVEL_ALIASES.get(low, low if low in LEVELS else '')


def _norm_evidence(value):
    low = str(value or '').strip().lower().replace('-', ' ').replace('_', ' ')
    if not low:
        return ''
    for alias in sorted(EVIDENCE_ALIASES, key=len, reverse=True):
        if alias in low:
            return EVIDENCE_ALIASES[alias]
    return ''


def _int_score(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return int(max(0, min(100, round(num))))


def _clamp01(value, default=0.0):
    """Tolerant 0-1 (or 0-100) confidence parsing."""
    if value is None or value == '':
        return default
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num > 1:
        num = num / 100.0
    return round(max(0.0, min(1.0, num)), 2)


def _upload(data, mime, key):
    """Upload a large video with the File API and return its URI when ready."""
    request = urllib.request.Request(
        f'{API_ROOT}/upload/v1beta/files?key={key}',
        data=data,
        method='POST',
        headers={
            'Content-Type': mime,
            'Content-Length': str(len(data)),
            'X-Goog-Upload-Protocol': 'raw',
            'X-Goog-Upload-Command': 'upload, finalize',
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        info = json.loads(response.read().decode('utf-8'))
    file_name = (info.get('file') or {}).get('name')
    return _wait_active(file_name, key) if file_name else ''


def _wait_active(file_name, key):
    url = f'{API_ROOT}/v1beta/{file_name}?key={key}'
    for _ in range(POLL_ATTEMPTS):
        with urllib.request.urlopen(url, timeout=60) as response:
            info = json.loads(response.read().decode('utf-8'))
        if info.get('state') == 'ACTIVE':
            return info.get('uri') or ''
        if info.get('state') == 'FAILED':
            return ''
        time.sleep(POLL_SECONDS)
    return ''


def _post_json(url, payload, timeout=180):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _first_text(result):
    for candidate in result.get('candidates') or []:
        for part in (candidate.get('content') or {}).get('parts') or []:
            if part.get('text'):
                return part['text']
    return ''


def _parse_json(text):
    """Pull the JSON object out of the model's reply (it may add prose/fences)."""
    text = text or ''
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return {}
