"""Small, privacy-conscious Gemini adapter for the public help assistant."""
import hashlib
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache


MAX_QUESTION_LENGTH = 600
MAX_REQUESTS_PER_MINUTE = 8

# Product documentation sent with each chat request. Keep this grounded in
# implemented flows; the assistant does not receive live account/database data.
SITE_KNOWLEDGE = """
KAAMSETU PRODUCT GUIDE (verified app behavior)

Purpose: KaamSetu connects local workers with employers in India. It supports
worker and employer accounts, local-language UI, job discovery, applications,
skill profiles, hiring consent, and basic listing safety checks. The interface
uses simple step-by-step forms for people with different education levels.

PUBLIC PAGES: Home /, About /about/, How it works /how-it-works/, choose role
/select-role/, Privacy /privacy/, Terms /terms/. Create an account from Register
and choose Worker or Employer. Sign in with Login. Never ask users to share
passwords, OTPs, bank details, or identity documents in chat.

WORKER FLOW: Dashboard /worker/dashboard/; profile /worker/profile/; upload a
work sample /worker/video/; review AI skill analysis /worker/skills/; browse
recommended jobs /worker/jobs/; applications /worker/applications/;
notifications /worker/notifications/; preferences /worker/settings/.
Complete profile details such as skills, experience, location, availability,
and work preferences to improve discovery. Browse a job, open its details, and
apply; a worker can save a job and withdraw an application. Application states
include Applied, Under Review, Shortlisted, Interview, Selected, Rejected, and
Hired. The assistant cannot see which jobs this user applied to or their current
application status.

SKILL VIDEO: Workers can upload a short video showing practical work. If the
Gemini vision key is configured, the app can suggest skills from it; the worker
reviews/accepts suggestions before they are treated as accepted profile skills.
Without that separate vision key, AI video analysis may be unavailable. A
suggested skill is not a certificate or proof of qualification.

EMPLOYER FLOW: Dashboard /employer/dashboard/; post a job
/employer/jobs/new/; manage jobs /employer/jobs/; discover workers
/employer/workers/; applications /employer/applications/; hired workers
/employer/hired/; feedback /employer/feedback/; notifications
/employer/notifications/; settings /employer/settings/. A listing asks for a
title, location, work type, wage range, skills, and a useful description. The
employer can review candidates and update application stages. Hiring is tied to
a worker-approved connection flow; do not promise an employer can bypass that
consent step. Worker profile visibility settings affect discovery. In a hiring
connection, workers can approve or decline requested profile details such as
contact information, education, skills, or video.

MATCHING AND SAFETY: Recommendations use practical matching signals such as
skills, location/distance, wage, availability, and trust signals. This is a
heuristic ranking, not a guarantee, an employment decision, or a promise of a
job. Listing checks are rule-based and can flag upfront fees, suspicious
phrases, unusually high wages, or missing details; they cannot guarantee a
listing or person is safe. Never call a user or listing verified. Tell users to
avoid paying to get a job, verify details independently, and report suspicious
activity through available support channels.

CHAT AND VOICE: The help chatbot is a separate optional Gemini integration. It
answers general KaamSetu/how-to questions but cannot access a user's profile,
applications, employer records, or change data. If AI is not configured or is
temporarily unavailable, tell the user to try later or contact
support@kaamsetu.in. Voice buttons use browser speech recognition to convert
speech into form text when the browser/device supports it; users should review
the transcription before submitting. Voice recognition may require browser
permission and may not work in every language/browser.

PRIVACY / LIMITS: Do not infer account facts. Do not invent page links, fees,
policies, guarantees, or support hours. If asked about a page not listed here,
give the closest known navigation path or say you are unsure and direct them to
support@kaamsetu.in. Answer in the user's chosen language and script, with
simple concise steps. If unrelated to KaamSetu or work, politely redirect.
"""


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
        'en': 'English', 'hi': 'Hindi', 'mr': 'Marathi', 'bn': 'Bangla',
        'ta': 'Tamil', 'te': 'Telugu', 'gu': 'Gujarati', 'kn': 'Kannada',
        'ml': 'Malayalam', 'pa': 'Punjabi', 'or': 'Odia', 'as': 'Assamese',
        'ur': 'Urdu', 'ne': 'Nepali', 'bho': 'Bhojpuri', 'mai': 'Maithili',
        'kok': 'Konkani', 'doi': 'Dogri', 'sa': 'Sanskrit', 'sd': 'Sindhi',
        'ks': 'Kashmiri', 'mni': 'Meitei (Manipuri)', 'brx': 'Bodo', 'sat': 'Santali',
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
    ) + SITE_KNOWLEDGE + '\n' + (
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
