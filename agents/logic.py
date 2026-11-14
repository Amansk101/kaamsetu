"""
KaamSetu AI agents — V1 heuristic engine.

Ye module PRD ke agents ko implement karta hai (Onboarding / Employer Intake /
Listing Verification / Skill Assessment / Matching / Follow-up / Bias audit).
Sabhi agents ek hi interface ke peeche hain, aur AGENT_MODE = 'llm' karke
V2 me real LLM/vision/STT providers plug kiye ja sakte hain.

Skill Assessment ab dynamic hai: `agents.vision` Gemini se profession aur
multi-skill evidence nikaalta hai, aur yahan wahi structured report banta hai.
Vision available na ho to ek clearly-labelled rule-based fallback chalta hai
jo kabhi bhi score invent nahi karta.
"""
import math
import re
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from agents.models import AgentLog

# ----------------------------------------------------------------------------
# Skill synonyms (local language) -> master Skill name
# ----------------------------------------------------------------------------
SKILL_SYNONYMS = {
    'plumber': 'Plumber', 'plumbing': 'Plumber', 'pipe': 'Plumber',
    'electrician': 'Electrician', 'bijli': 'Electrician', 'wire': 'Electrician',
    'mason': 'Mason', 'mistri': 'Mason', 'raj mistri': 'Mason', 'chipai': 'Mason',
    'painter': 'Painter', 'paint': 'Painter', 'rang': 'Painter',
    'driver': 'Driver', 'driving': 'Driver', 'gaadi': 'Driver',
    'carpenter': 'Carpenter', 'badhai': 'Carpenter', 'furniture': 'Carpenter',
    'welder': 'Welder', 'welding': 'Welder',
    'tailor': 'Tailor', 'darzi': 'Tailor', 'silai': 'Tailor',
    'cook': 'Cook', 'cooking': 'Cook', 'khana': 'Cook', 'rasoi': 'Cook',
    'guard': 'Security Guard', 'security': 'Security Guard', 'chowkidar': 'Security Guard',
    'helper': 'Helper', 'mazdoor': 'Helper', 'labour': 'Helper', 'laborer': 'Helper',
    'farmer': 'Farm Labour', 'kheti': 'Farm Labour', 'farm': 'Farm Labour',
    'cleaning': 'Housekeeping', 'housekeeping': 'Housekeeping', 'safai': 'Housekeeping',
}


def detect_skill(*texts):
    """Detect the most likely skill from any available text (e.g. video file name).

    This is only a weak naming hint used by the rule-based fallback — the real
    discovery happens in ``agents.vision``. Returns the canonical skill name,
    or an empty string when nothing matches.
    """
    haystack = ' '.join(str(text or '') for text in texts).lower()
    if not haystack:
        return ''
    # Longest keyword first so "raj mistri" wins over "mistri".
    for keyword in sorted(SKILL_SYNONYMS, key=len, reverse=True):
        if keyword in haystack:
            return SKILL_SYNONYMS[keyword]
    return ''


# Fraud / scam signal keywords (worker ko paisa maangna = hard block)
FRAUD_BLOCK_KEYWORDS = [
    'registration fee', 'registration charge', 'joining fee', 'advance payment',
    'advance do', 'pehle paisa', 'paisa pehle', 'deposit', 'security deposit',
    'fee do', 'fees dena', 'paisa bhejo', 'paise bhejo', 'refundable',
    'charge lagega', 'form fee', 'application fee', 'training fee',
]
FRAUD_WARN_KEYWORDS = [
    'urgent', 'no experience', 'no documents', 'anyone can apply',
    'work from home', 'daily payout', 'instant joining', 'limited seats',
]

_UNAVAILABLE_LOCATION_NOTE = 'Location coordinates missing — approximate match'

# WorkerSkill / profile levels (3) plus the richer AI discovery levels (4).
_LEVEL_WEIGHT = {
    'beginner': 0.5, 'working': 0.8, 'skilled': 1.0,
    'intermediate': 0.7, 'advanced': 0.9, 'expert': 1.0,
}
# AI discovery level -> the level stored on the public profile.
PROFILE_LEVEL_MAP = {
    'beginner': 'beginner', 'intermediate': 'working',
    'advanced': 'skilled', 'expert': 'skilled',
}
AI_LEVELS = ('beginner', 'intermediate', 'advanced', 'expert')
PROFILE_LEVELS = ('beginner', 'working', 'skilled')
# Evidence states that carry a real, evidence-based score.
ASSESSABLE_EVIDENCE = ('observed', 'partial')
_EVIDENCE_LABELS = {
    'observed': 'Observed',
    'partial': 'Partly observed',
    'claimed': 'Claimed only',
    'insufficient': 'Not enough evidence',
}


def log_agent(agent, subject_type='', subject_id='', input_summary='', output=None):
    """Har agent run ka transparent record rakho (bias audit + debugging)."""
    try:
        AgentLog.objects.create(
            agent=agent,
            subject_type=subject_type,
            subject_id=str(subject_id),
            input_summary=(input_summary or '')[:2000],
            output=output or {},
        )
    except Exception:  # logging kabhi main flow ko na tode
        pass


# ----------------------------------------------------------------------------
# 1. Employer Intake Agent — free text/voice -> structured listing
# ----------------------------------------------------------------------------
def parse_job_listing(text):
    from core.models import Area, Skill

    text = (text or '').strip()
    low = text.lower()
    data = {
        'title': '',
        'skill_name': '',
        'workers_needed': 1,
        'wage_min': None,
        'wage_max': None,
        'wage_period': 'day',
        'area_name': '',
        'job_type': 'full_time',
    }

    # Skill detect
    for key, canonical in SKILL_SYNONYMS.items():
        if key in low:
            data['skill_name'] = canonical
            break
    if not data['skill_name']:
        for skill in Skill.objects.all():
            if skill.name.lower() in low:
                data['skill_name'] = skill.name
                break

    # Numbers -> wage vs worker count
    number_values = [int(n) for n in re.findall(r'\b\d+\b', text.replace(',', ''))]
    wages = sorted(n for n in number_values if n >= 100)
    if wages:
        data['wage_min'] = wages[0]
        data['wage_max'] = wages[-1]

    # Worker count ("2 plumber", "do log")
    word_nums = {'ek': 1, 'do': 2, 'teen': 3, 'char': 4, 'paanch': 5, 'panch': 5}
    counts = [n for n in number_values if 0 < n < 100]
    if counts:
        data['workers_needed'] = counts[0]
    else:
        for w, n in word_nums.items():
            if re.search(r'\b' + w + r'\b', low):
                data['workers_needed'] = n
                break

    # Wage period
    if re.search(r'\b(month|monthly|mahina|mahine)\b', low):
        data['wage_period'] = 'month'
    elif re.search(r'\b(hour|hourly|ghanta)\b', low):
        data['wage_period'] = 'hour'
    else:
        data['wage_period'] = 'day'

    # Job type
    if re.search(r'\b(season|seasonal|mausam|temporary)\b', low):
        data['job_type'] = 'seasonal'
    elif re.search(r'\b(part time|part-time|aadha)\b', low):
        data['job_type'] = 'part_time'
    elif re.search(r'\b(contract|theka)\b', low):
        data['job_type'] = 'contract'

    # Area detect
    for area in Area.objects.all():
        if area.name and area.name.lower() in low:
            data['area_name'] = area.name
            break

    # Title
    sk = data['skill_name'] or 'Worker'
    data['title'] = f'{sk} required' if data['skill_name'] else 'Worker required'
    if data['area_name']:
        data['title'] += f' - {data["area_name"]}'

    log_agent('EmployerIntakeAgent', 'job_text', '', text[:400], data)
    return data


# ----------------------------------------------------------------------------
# 2. Listing Verification Agent — fraud scoring
# ----------------------------------------------------------------------------
def verify_listing(raw_text, structured):
    low = (raw_text or '').lower()
    flags = []
    risk = 0

    for kw in FRAUD_BLOCK_KEYWORDS:
        if kw in low:
            flags.append({'type': 'block', 'label': f'Upfront payment requested: "{kw}"'})
            risk += 55

    for kw in FRAUD_WARN_KEYWORDS:
        if kw in low:
            flags.append({'type': 'warn', 'label': f'Suspicious phrase: "{kw}"'})
            risk += 8

    # Unrealistic wage for daily labour
    wage_max = structured.get('wage_max')
    if structured.get('wage_period') == 'day' and wage_max and wage_max > 5000:
        flags.append({'type': 'warn', 'label': f'Unusually high daily wage: ₹{wage_max}'})
        risk += 20

    if not structured.get('skill_name'):
        flags.append({'type': 'info', 'label': 'Skill is not clearly mentioned'})
        risk += 5

    if not structured.get('wage_min') and not structured.get('wage_max'):
        flags.append({'type': 'info', 'label': 'Wage is not mentioned'})
        risk += 5

    risk = min(100, risk)
    has_block = any(f['type'] == 'block' for f in flags)

    if has_block:
        status = 'blocked'
        summary = 'Blocked: the listing asks the worker for an upfront payment.'
    elif risk >= 30:
        status = 'flagged'
        summary = 'Needs manual review — a few suspicious signals were found.'
    else:
        status = 'passed'
        summary = 'Listing is safe — no fraud signals were found.'

    result = {'status': status, 'risk_score': risk, 'flags': flags, 'summary': summary}
    log_agent('ListingVerificationAgent', 'listing', '', raw_text[:400], result)
    return result


# ----------------------------------------------------------------------------
# 3. Skill Assessment Agent — video -> dynamic multi-skill report
# ----------------------------------------------------------------------------
def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dedupe(items, limit=6):
    """Clean, de-duplicated list of short strings."""
    out, seen = [], set()
    for item in items or []:
        text = str(item or '').strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _length_signal(dur):
    if dur >= 30:
        return 1.0, 'good', f'{dur} seconds — the full demo is visible.'
    if dur >= 15:
        return 0.75, 'info', f'{dur} seconds — the demo is visible but a little more detail would help.'
    if dur > 0:
        return 0.4, 'warn', f'{dur} seconds — the video is too short to show the work clearly.'
    return 0.3, 'warn', 'The video duration could not be detected.'


def _speech_block(ai):
    """Normalise the vision model's audio analysis into a template-friendly block."""
    has_speech = bool(ai.get('has_speech'))
    quality = str(ai.get('speech_quality') or 'none').strip().lower()
    correct = ai.get('speech_correct') if has_speech else None
    label = {'clear': 'Clear', 'unclear': 'Unclear'}.get(quality, 'No speech')
    tone = {'clear': 'good', 'unclear': 'warn'}.get(quality, 'info')
    return {
        'has_speech': has_speech,
        'transcript': str(ai.get('transcript') or '').strip(),
        'language': str(ai.get('speech_language') or '').strip(),
        'quality': quality if has_speech else 'none',
        'quality_label': label if has_speech else 'No speech',
        'correct': correct,
        'feedback': str(ai.get('speech_feedback') or '').strip(),
        'tone': tone if has_speech else 'info',
    }


def _overall_level(overall):
    """Map an average 0-100 score onto the public 3-level profile scheme."""
    if overall >= 75:
        return 'skilled'
    if overall >= 45:
        return 'working'
    return 'beginner'


def _skill_row(raw):
    """Turn one normalised vision skill into a template/storage friendly dict."""
    status = str(raw.get('evidence_status') or 'insufficient')
    ai_level = str(raw.get('level') or '')
    score = raw.get('score')
    assessable = status in ASSESSABLE_EVIDENCE and score is not None
    return {
        'name': str(raw.get('name') or 'Skill')[:80],
        'description': str(raw.get('description') or ''),
        'category': str(raw.get('category') or ''),
        'score': int(score) if assessable else None,
        'level': ai_level if assessable else '',
        'confidence': raw.get('confidence'),
        'reason': str(raw.get('reason') or ''),
        'strengths': _dedupe(raw.get('strengths'), 8),
        'improvements': _dedupe(raw.get('improvements'), 8),
        'recommendations': _dedupe(raw.get('recommendations'), 8),
        'evidence': _dedupe(raw.get('evidence'), 8),
        'limitations': str(raw.get('limitations') or ''),
        'evidence_status': status,
        'is_assessable': assessable,
        'profile_level': PROFILE_LEVEL_MAP.get(ai_level, 'beginner'),
        'level_label': ai_level.title() if assessable else _EVIDENCE_LABELS.get(status, status.title()),
    }


def assess_skill_video(duration_seconds, self_level='beginner', skill_name='', filename='', vision=None):
    """
    Build the skill report for one uploaded video.

    ``vision`` is the result of ``agents.vision.analyze()``. When the model
    actually watched the video it reports the profession plus one entry per
    discovered skill (score, level, evidence strength, reason, strengths,
    improvements, recommendations, evidence, limitations) and each skill is
    scored independently here. Without vision output a clearly labelled
    rule-based fallback runs that never invents a score.
    """
    ai = vision or {}
    skills = ai.get('skills')
    has_skills = isinstance(skills, (list, tuple)) and bool(skills)
    if has_skills or ai.get('profession'):
        result = _ai_report(duration_seconds, self_level, ai)
    else:
        result = _rule_based_report(duration_seconds, self_level, skill_name, filename)
    log_agent('SkillAssessmentAgent', 'worker', '', result['notes'][:400], {
        'source': result['source'],
        'overall': result['overall'],
        'level': result['level'],
        'skills': [s['name'] for s in result['skills']],
    })
    return result


def _ai_report(duration_seconds, self_level, ai):
    """Multi-skill report built from what the vision model actually saw."""
    dur = int(duration_seconds or 0)
    rows = [_skill_row(s) for s in (ai.get('skills') or []) if isinstance(s, dict)]
    assessable = [r for r in rows if r['is_assessable']]
    scores = [r['score'] for r in assessable]

    overall = round(sum(scores) / len(scores)) if scores else 0
    level = _overall_level(overall) if scores else ''
    confidence = (
        round(sum(_as_float(r['confidence']) for r in assessable) / len(assessable), 2)
        if assessable else _as_float(ai.get('profession_confidence'))
    )

    length_score, length_tone, length_note = _length_signal(dur)
    profession = str(ai.get('profession') or '').strip()
    speech = _speech_block(ai)

    signals = []
    if profession:
        signals.append({
            'label': 'Profession detected',
            'value': profession,
            'tone': 'good',
            'note': str(ai.get('work_summary') or '').strip() or 'The work the AI recognised in the video.',
        })
    signals.append({
        'label': 'Skills discovered',
        'value': str(len(rows)),
        'tone': 'good' if rows else 'warn',
        'note': 'Different skills the AI found in this single video.',
    })
    signals.append({
        'label': 'Rated from evidence',
        'value': f'{len(assessable)} of {len(rows)}' if rows else '0',
        'tone': 'good' if assessable else 'warn',
        'note': 'Only skills the AI could actually see performed are scored.',
    })
    signals.append({
        'label': 'Video length',
        'value': f'{dur}s',
        'tone': length_tone,
        'note': length_note,
    })
    signals.append({
        'label': 'AI model',
        'value': str(ai.get('model') or 'Gemini'),
        'tone': 'info',
        'note': 'The vision model that watched and listened to your video.',
    })
    if speech['has_speech']:
        signals.append({
            'label': 'Speech',
            'value': speech['quality_label'],
            'tone': speech['tone'],
            'note': speech['feedback'] or 'The AI transcribed and checked the words spoken in the video.',
        })

    strengths = _dedupe([s for r in assessable for s in r['strengths']], 8)
    improvements = _dedupe([s for r in rows for s in r['improvements']], 8)
    recommendations = _dedupe([s for r in rows for s in r['recommendations']], 8)
    insufficient_notes = _dedupe(ai.get('insufficient_notes'), 6)

    for r in rows:
        if not r['is_assessable']:
            insufficient_notes.append(
                f'{r["name"]}: {_EVIDENCE_LABELS.get(r["evidence_status"], "limited evidence").lower()} '
                f'— no score was given.'
            )
    insufficient_notes = _dedupe(insufficient_notes, 8)

    if speech['has_speech']:
        if speech['correct']:
            strengths.append('Your spoken explanation matched the work you were doing.')
        elif speech['quality'] == 'clear':
            strengths.append('You explained your work clearly on camera.')
        if speech['correct'] is False:
            improvements.append('What you said did not fully match the work shown — describe the steps as you do them.')
        if speech['quality'] == 'unclear':
            improvements.append('Speak clearly and a little slower so your explanation is easy to follow.')
    else:
        improvements.append('Add a short voice explanation of what you are doing while you work.')

    if dur < 15:
        improvements.insert(0, 'Record a 15–30 second longer video showing the complete task.')
    improvements = _dedupe(improvements, 8)

    training = list(recommendations) or ['Practice the task end to end and record it again.']

    next_steps = [
        'Review the detected skills below and accept the ones that really are your work.',
        'Accepted skills appear on your public profile for employers.',
    ]
    for r in rows:
        if not r['is_assessable']:
            next_steps.append(
                f'Record a longer, clearer video that shows "{r["name"]}" step by step to get it rated.'
            )

    if not rows:
        summary = 'The AI watched the video but could not clearly identify a specific skill in it.'
    else:
        rated = ', '.join(f'{r["name"]} ({r["score"]}/100)' for r in assessable[:3])
        summary = (
            f'The AI identified {profession or "your work"} in the video and found '
            f'{len(rows)} skill(s). ' + (f'Rated: {rated}. ' if rated else '')
            + f'Overall {overall}/100 ({level.title() or "not rated"}).'
        ).strip()
    if str(ai.get('overall_summary') or '').strip():
        summary = str(ai['overall_summary']).strip()

    notes_lines = [
        f'AI video analysis — profession: {profession or "unknown"}',
        f'Overall score: {overall}/100  ·  Level: {level.title() or "not rated"}  ·  '
        f'Confidence: {int(confidence * 100)}%',
        f'- Video length: {length_note}',
        f'- Skills discovered: {len(rows)}  ·  Rated from evidence: {len(assessable)}',
    ]
    for r in rows:
        notes_lines.append(
            f'- {r["name"]}: '
            + (f'{r["score"]}/100, {r["level"]}, confidence {int(_as_float(r["confidence"]) * 100)}%'
               if r['is_assessable'] else _EVIDENCE_LABELS.get(r['evidence_status'], 'no score'))
            + (f' | {r["reason"]}' if r['reason'] else '')
        )
    if insufficient_notes:
        notes_lines.append('- Not enough evidence: ' + '; '.join(insufficient_notes))
    if speech['has_speech']:
        notes_lines.append(
            f'- Speech quality: {speech["quality_label"]}'
            + (f' ({speech["language"]})' if speech['language'] else '')
        )
        notes_lines.append(
            '- Speech matches the work: '
            + ('yes' if speech['correct'] else 'no' if speech['correct'] is False else 'unclear')
        )
        if speech['transcript']:
            notes_lines.append(f'- Spoken words: "{speech["transcript"]}"')
    else:
        notes_lines.append('- Speech quality: no speech detected in the video')
    notes_lines += [
        'Strengths: ' + '; '.join(strengths),
        'Improvements: ' + '; '.join(improvements),
        'Recommendations: ' + '; '.join(training),
        f'(Analysed by the vision AI model {ai.get("model") or "Gemini"}.)',
    ]

    return {
        'source': 'ai',
        'provider': str(ai.get('provider') or 'gemini'),
        'model': str(ai.get('model') or ''),
        'is_ai': True,
        'profession': profession,
        'profession_confidence': _as_float(ai.get('profession_confidence')),
        'work_summary': str(ai.get('work_summary') or '').strip(),
        'overall': overall,
        'level': level,
        'confidence': confidence,
        'duration': dur,
        'skills': rows,
        'skill': rows[0]['name'] if rows else profession,
        'skill_detail': '',
        'sub_skills': [r['name'] for r in rows][:8],
        'assessable_count': len(assessable),
        'skill_count': len(rows),
        'insufficient_notes': insufficient_notes,
        'speech': speech,
        'signals': signals,
        'strengths': strengths or ['You uploaded a work sample — that is the right first step.'],
        'improvements': improvements,
        'recommendations': recommendations,
        'training': training,
        'next_steps': _dedupe(next_steps, 6),
        'summary': summary,
        'notes': '\n'.join(notes_lines),
    }


def _rule_based_report(duration_seconds, self_level, skill_name, filename):
    """Honest fallback when no vision model watched the video.

    No score is ever produced here — without a model actually watching the
    video there is no evidence to rate, so the skill is marked as *claimed*
    and the UI labels the whole report as rule-based.
    """
    dur = int(duration_seconds or 0)
    length_score, length_tone, length_note = _length_signal(dur)
    declared = self_level if self_level in PROFILE_LEVELS else 'beginner'
    name = (skill_name or '').strip() or detect_skill(filename)

    rows = []
    if name:
        rows.append({
            'name': name,
            'description': '',
            'category': '',
            'score': None,
            'level': '',
            'confidence': None,
            'reason': (
                'This skill comes from your selection or the video file name — '
                'the video itself was not analysed, so no score is given.'
            ),
            'strengths': [],
            'improvements': [],
            'recommendations': [],
            'evidence': [],
            'limitations': 'No AI video analysis was run for this upload.',
            'evidence_status': 'claimed',
            'is_assessable': False,
            'profile_level': 'beginner',
            'level_label': _EVIDENCE_LABELS['claimed'],
        })

    signals = [
        {
            'label': 'Declared level',
            'value': declared.title(),
            'tone': 'info',
            'note': f'You described yourself as "{declared.title()}".',
        },
        {
            'label': 'Video length',
            'value': f'{dur}s',
            'tone': length_tone,
            'note': length_note,
        },
        {
            'label': 'Report type',
            'value': 'Rule-based',
            'tone': 'warn',
            'note': 'No AI model watched this video — no skill score can be given from it.',
        },
    ]

    strengths = [
        'You uploaded a work sample — that is the right first step',
        'Shows willingness to make your skills visible to employers',
    ]
    improvements = [
        'Turn on AI analysis (add KAAMSETU_GEMINI_API_KEY) and re-upload so a model can actually watch the work.',
        'Record a 15–30 second video showing the complete task in good light.',
        'Add a short voice explanation of what you are doing while you work.',
    ]
    training = ['A short course on the basics of the work you demonstrated.']
    next_steps = [
        'Re-upload the video once AI analysis is enabled to get a real skill rating.',
        'Keep your profile skills up to date in the meantime.',
    ]

    summary = (
        'This is a rule-based estimate — no AI model watched the video, so no skill '
        'score was given. Add KAAMSETU_GEMINI_API_KEY and re-upload for a real, '
        'evidence-based analysis of your work and speech.'
    )

    notes_lines = [
        'Rule-based fallback report — no vision model watched this video.',
        f'- Video length: {length_note}',
        f'- Declared level: {declared.title()}',
        f'- Skill: {name or "not detected"} (claimed only — no score)',
        'Strengths: ' + '; '.join(strengths),
        'Improvements: ' + '; '.join(improvements),
        '(Rule-based analysis — set KAAMSETU_GEMINI_API_KEY for full AI video + speech analysis.)',
    ]

    return {
        'source': 'rule_based',
        'provider': '',
        'model': '',
        'is_ai': False,
        'profession': '',
        'profession_confidence': 0.0,
        'work_summary': '',
        'overall': 0,
        'level': '',
        'confidence': 0.0,
        'duration': dur,
        'skills': rows,
        'skill': name,
        'skill_detail': '',
        'sub_skills': [],
        'assessable_count': 0,
        'skill_count': len(rows),
        'insufficient_notes': [
            'No AI model watched this video, so none of the skills could be evidenced.'
        ],
        'speech': _speech_block({}),
        'signals': signals,
        'strengths': strengths,
        'improvements': improvements,
        'recommendations': [],
        'training': training,
        'next_steps': next_steps,
        'summary': summary,
        'notes': '\n'.join(notes_lines),
    }


# ----------------------------------------------------------------------------
# 4. Matching Agent — skill + distance + wage + trust
# ----------------------------------------------------------------------------
def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _distance_km(worker, job):
    wa, ja = worker.area, job.area
    if not wa or not ja:
        return None
    if wa.pk == ja.pk:
        return 0.0
    if wa.latitude and wa.longitude and ja.latitude and ja.longitude:
        return round(_haversine_km(wa.latitude, wa.longitude, ja.latitude, ja.longitude), 1)
    if wa.district and wa.district == ja.district:
        return 5.0
    return None


def match_score(worker, job):
    """Return (score 0-100, list_of_reason_strings). Protected attributes exclude."""
    weights = settings.KAAMSETU['MATCH_WEIGHTS']
    max_km = settings.KAAMSETU['MATCH_MAX_DISTANCE_KM']
    reasons = []

    # --- Skill ---
    if job.skill_id:
        ws = worker.skills.filter(skill_id=job.skill_id).first()
        if ws:
            skill_score = _LEVEL_WEIGHT.get(ws.level, 0.5)
            if ws.verified:
                skill_score = min(1.0, skill_score + 0.1)
                reasons.append(f'Verified skill: {job.skill} ({ws.get_level_display()})')
            else:
                reasons.append(f'Skill match: {job.skill} ({ws.get_level_display()})')
        else:
            skill_score = 0.15
    else:
        skill_score = 0.6

    # --- Distance ---
    dist = _distance_km(worker, job)
    if dist is None:
        dist_score = 0.4
    else:
        dist_score = max(0.0, 1.0 - (dist / max_km))
        if dist <= worker.max_travel_km:
            reasons.append(f'{dist:g} km away — within travel range')
        else:
            reasons.append(f'{dist:g} km away — outside travel range')

    # --- Wage ---
    if job.wage_max and worker.expected_min_wage:
        if job.wage_max >= worker.expected_min_wage:
            wage_score = 1.0
            reasons.append(f'Wage ₹{job.wage_max}/{(job.wage_period or "day")} — above your expectation')
        else:
            wage_score = max(0.2, job.wage_max / worker.expected_min_wage)
    else:
        wage_score = 0.6

    # --- Trust ---
    ver = getattr(job, 'verification', None)
    if ver and ver.status == 'passed':
        trust_score = 1.0
        reasons.append('Listing passed the rule-based safety check')
    elif ver and ver.status == 'flagged':
        trust_score = 0.4
        reasons.append('Listing flagged — review pending')
    else:
        trust_score = 0.6

    # --- Availability (light nudge) ---
    avail = {'immediate': 1.0, 'week': 0.8, 'flexible': 0.7}.get(worker.availability, 0.8)

    total = (
        weights['skill'] * skill_score
        + weights['distance'] * dist_score
        + weights['wage'] * wage_score
        + weights['trust'] * trust_score
    ) / sum(weights.values())
    total = total * (0.7 + 0.3 * avail)

    return round(total * 100), reasons


def top_jobs_for_worker(worker, limit=6):
    from jobs.models import Job

    jobs = Job.objects.filter(status=Job.Status.ACTIVE).select_related(
        'skill', 'area', 'employer', 'verification'
    )
    scored = []
    for job in jobs:
        score, reasons = match_score(worker, job)
        scored.append({'job': job, 'score': score, 'reasons': reasons})
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:limit]


def matched_workers_for_job(job, limit=12):
    from workers.models import WorkerProfile

    if job.skill_id:
        workers = WorkerProfile.objects.filter(skills__skill_id=job.skill_id).distinct()
    else:
        workers = WorkerProfile.objects.all()
    scored = []
    for w in workers:
        score, reasons = match_score(w, job)
        if score >= 40:
            scored.append({'worker': w, 'score': score, 'reasons': reasons})
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:limit]


# ----------------------------------------------------------------------------
# 5. Follow-up / Retention Agent
# ----------------------------------------------------------------------------
def schedule_followups(connection):
    from hiring.models import FollowUp

    base = (connection.hired_at or timezone.now()).date()
    created = []
    for stage, days in (('day7', 7), ('day30', 30), ('day90', 90)):
        fu, made = FollowUp.objects.get_or_create(
            connection=connection,
            stage=stage,
            defaults={'due_date': base + timedelta(days=days)},
        )
        if made:
            created.append(fu)
    log_agent('FollowUpAgent', 'connection', connection.pk, '',
              {'scheduled': [f.stage for f in created]})
    return created


# ----------------------------------------------------------------------------
# 6. Bias Auditor — protected attributes matching me use nahi hote
# ----------------------------------------------------------------------------
PROTECTED_ATTRIBUTES = ['full_name', 'gender', 'photo', 'caste', 'religion', 'age']


def bias_audit(matches):
    scores = [m['score'] for m in matches] or [0]
    result = {
        'matches': len(matches),
        'avg_score': round(sum(scores) / len(scores), 1),
        'excluded_attributes': PROTECTED_ATTRIBUTES,
        'note': 'Ranking uses skill, distance, wage and trust only — protected attributes are excluded.',
    }
    log_agent('BiasAuditor', 'match_batch', '', '', result)
    return result
