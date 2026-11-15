"""Small, privacy-conscious Gemini adapter for the public help assistant."""
import hashlib
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache


MAX_QUESTION_LENGTH = 600
MAX_REQUESTS_PER_MINUTE = 8


def ai_is_enabled():
    return bool(settings.KAAMSETU.get('GEMINI_API_KEY'))


def _under_rate_limit(client_ip):
    """Limit use of the free provider quota without saving question text."""
    key_hash = hashlib.sha256((client_ip or 'unknown').encode('utf-8')).hexdigest()[:32]
    key = f'kaamsetu-chat-rate:{key_hash}'
    try:
        if cache.add(key, 1, timeout=60):
            return True
        try:
            return cache.incr(key) <= MAX_REQUESTS_PER_MINUTE
        except ValueError:
            return cache.add(key, 1, timeout=60)
    except Exception:
        # If rate-limit storage fails, keep the assistant usable; the model
        # call still has a strict input/output limit and short timeout.
        return True


def answer_question(question, role, language, history=None):
    """Send one user question to the configured Gemini free-tier model.

    The app does not persist prompts or answers. Only the question, role, and
    UI language are sent to Google's API; never include profile data here.
    """
    config = settings.KAAMSETU
    api_key = str(config.get('GEMINI_API_KEY') or '').strip()
    if not api_key:
        return ''

    model = str(config.get('CHATBOT_MODEL') or 'gemini-3.5-flash-lite').strip()
    if not model.replace('-', '').replace('.', '').isalnum():
        return ''
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    language_names = {
        'hi': 'Hindi', 'en': 'English', 'mr': 'Marathi', 'bn': 'Bangla',
        'ta': 'Tamil', 'te': 'Telugu', 'gu': 'Gujarati', 'kn': 'Kannada',
        'ml': 'Malayalam', 'pa': 'Punjabi', 'ur': 'Urdu', 'bho': 'Bhojpuri',
    }
    language_name = language_names.get(language, 'simple English')
    role_name = role if role in {'worker', 'employer'} else 'visitor'
    system_instruction = (
        'You are KaamSetu Help, a concise and kind assistant for workers and small employers in India. '
        'Answer the user in ' + language_name + ' using short, plain language, and match the script the user uses '
        '(for example, use Roman Hindi if they write Hinglish). '
        'Help with using KaamSetu, finding/posting jobs, profiles, applications, skill videos, consent, '
        'and basic safe-work guidance. You cannot see the user account or change anything. '
        'Never claim a job, employer, worker, payment, or account has been verified. '
        'Never ask for passwords, OTPs, bank details, or sensitive personal information. '
        'For account-specific or unresolved problems, tell them to contact support@kaamsetu.in. '
        'Known pages: worker profile /worker/profile/, worker jobs /worker/jobs/, worker applications '
        '/worker/applications/, skill video /worker/video/, employer settings /employer/settings/, employer jobs '
        '/employer/jobs/, new job /employer/jobs/new/, employer applications /employer/applications/, privacy /privacy/. '
        'Do not invent other URLs. '
        'If unrelated to KaamSetu or finding work, briefly say you can only help with KaamSetu and work questions. '
        'Keep the reply under 100 words. The current user role is ' + role_name + '.'
    )
    contents = []
    for item in (history or [])[-6:]:
        if not isinstance(item, dict) or item.get('role') not in {'user', 'model'}:
            continue
        text = str(item.get('text') or '').strip()[:MAX_QUESTION_LENGTH]
        if text:
            contents.append({'role': item['role'], 'parts': [{'text': text}]})
    if not contents or contents[-1]['parts'][0]['text'] != question:
        contents.append({'role': 'user', 'parts': [{'text': question}]})
    payload = {
        'systemInstruction': {'parts': [{'text': system_instruction}]},
        'contents': contents,
        'generationConfig': {'temperature': 0.25, 'maxOutputTokens': 300},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'x-goog-api-key': api_key,
            'x-goog-api-client': 'kaamsetu-help/1.0',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            result = json.loads(response.read(128 * 1024).decode('utf-8'))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ''

    if not isinstance(result, dict):
        return ''
    for candidate in result.get('candidates') or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get('content')
        if not isinstance(content, dict):
            continue
        parts = content.get('parts') or []
        reply = ' '.join(
            part.get('text', '') for part in parts
            if isinstance(part, dict) and part.get('text')
        ).strip()
        if reply:
            return reply[:1800]
    return ''
