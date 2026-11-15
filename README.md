# KaamSetu (Django)

KaamSetu ek rural / local employment platform hai jo workers ko nearby job
opportunities se aur employers ko skilled local workers se connect karta hai.
Ye project reference React app **“KaamSetu”** ko Django me reproduce karta hai —
same branding, layout, routes, forms, worker/employer flows aur
English/Hindi/Marathi experience — Django templates + CSS + vanilla JS ke saath
(React ki zaroorat nahi).

---

## Tech stack

| Layer      | Choice |
|------------|--------|
| Framework  | Django 6.1.x (custom user model + built-in auth) |
| Templates  | Django templates, shared `base.html` + `partials/*` |
| Styling    | Ported CSS from the React app (`static/css/*`) |
| JS         | Vanilla JS (`static/js/kaamsetu.js`) + Lucide icons via CDN |
| Database   | SQLite (dev). Models Postgres-compatible (FKs, indexes, choices) |
| Media      | Django `MEDIA_ROOT` uploads (profile photos, skill videos) |
| i18n       | Custom lightweight translation layer: 24 Indian languages (English default) |

Passwords Django ke password hashers se hashed store hote hain — kabhi plain text nahi.

---

## Requirements

- Python 3.11+ (tested on 3.14)
- Django 6.1.x

```powershell
# (optional) virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate         # macOS / Linux

pip install -r requirements.txt
```

`requirements.txt` sirf zaroori runtime dependencies rakhta hai (`Django>=6.1,<7`).

---

## Setup & run (local)

```powershell
# 1) Migrations apply karo
python manage.py migrate

# 2) Dev server chalao
python manage.py runserver
# Browser me kholo: http://127.0.0.1:8000/
```

> App **khaali** start hota hai — koi sample/demo/static data nahi.
> Asli users hamesha `/accounts/register/` se banao.

Optional admin user:

```powershell
python manage.py createsuperuser
# Admin: http://127.0.0.1:8000/admin/
```

## Free demo hosting (Render)

The repository includes a Render Blueprint in `render.yaml`. It creates a free
web service and a free PostgreSQL database for a demo deployment:

1. Push the project to a GitHub repository and connect it to Render.
2. Click **Deploy Blueprint**; Render connects the web service to its PostgreSQL database.
3. To keep uploaded profile photos and skill videos, create an S3-compatible bucket
   (Cloudflare R2 has a monthly free allowance) and set the `KAAMSETU_R2_*` values
   listed in `render.yaml`. Keep the bucket private; the app generates signed media
   links when it serves uploaded files.
4. When the build finishes, open the service's `onrender.com` address.

Render's free web service sleeps when idle and its local filesystem is temporary.
Free Render Postgres expires after 30 days and the local `media/` folder is temporary,
so use this setup for a demo only. Configure separate durable database and object
storage before accepting real user data or uploads.

---

## AI skill analysis (video + speech)

Jab worker apna skills video upload karta hai, video ko **Google Gemini** vision
model par bheja jaata hai (`.env` me `KAAMSETU_GEMINI_API_KEY` set hona chahiye):

- video ko "dekh" kar **skill** aur uska **specific type** batata hai
  (jaise cooking -> "North Indian home cooking — roti and sabzi"),
- video me dikhi **techniques / sub-skills** list karta hai,
- **audio/speech analysis**: worker ne jo bola uska transcript banata hai aur
  batata hai ki speech **clear** hai ya nahi, aur jo bola wo **kaam se match**
  karta hai ya nahi,
- level, confidence aur short reasoning deta hai.

Key free milti hai: <https://aistudio.google.com/apikey>. Key na ho to app
chalta rehta hai (filename/heuristic fallback), lekin full AI video + speech
analysis tabhi milega jab key set ho.

```powershell
# .env
KAAMSETU_GEMINI_API_KEY=your-key
KAAMSETU_GEMINI_MODEL=gemini-3-flash-preview
```

---

## Media & static configuration

`config/settings.py`:

```python
STATIC_URL  = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']   # source CSS/JS/images yahan
STATIC_ROOT = BASE_DIR / 'staticfiles'     # collectstatic target (production)

MEDIA_URL  = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'            # uploaded photos & skill videos
```

- Development me static aur media dono Django se serve hote hain
  (`config/urls.py` me `static(settings.MEDIA_URL, ...)` sirf `DEBUG=True` par).
- Production ke liye: `python manage.py collectstatic` chalao aur `DEBUG=False`
  karke static/media ko web server / CDN se serve karo.
- Uploads: worker profile photo → `media/worker_photos/`,
  skill video → `media/skill_videos/`.

---

## Configuration & environment

Settings environment variables se aati hain (project root ki `.env` auto-load hoti
hai — `.env.example` ko copy karo). Development defaults aise hain ki bina kuch
set kiye app chalta rehta hai.

| Variable | Default (dev) | Purpose |
|----------|---------------|---------|
| `KAAMSETU_DEBUG` | `true` | `false` karne par production security on ho jaati hai |
| `KAAMSETU_SECRET_KEY` | dev fallback | **Production me zaroori** (DEBUG=false ho to missing key par app start hi nahi hota) |
| `KAAMSETU_ALLOWED_HOSTS` | `*` (dev) | Comma-separated hostnames |
| `KAAMSETU_CSRF_TRUSTED_ORIGINS` | — | HTTPS origins (production) |
| `KAAMSETU_SECURE_SSL` | `true` | HTTPS redirect toggle (sirf DEBUG=false par) |
| `KAAMSETU_GEMINI_API_KEY` | — | Vision AI (video + speech) ke liye |
| `KAAMSETU_GEMINI_MODEL` | `gemini-2.5-flash` | Vision model |
| `KAAMSETU_EMAIL_*` | — | SMTP; na ho to mail `sent_emails/` me file ban jaati hai |

`KAAMSETU_DEBUG=false` par automatically: `SECURE_SSL_REDIRECT`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS, `X_FRAME_OPTIONS=DENY`
aur `SECURE_CONTENT_TYPE_NOSNIFF` lag jaate hain.

**Logging**: console + `logs/kaamsetu.log` (rotating, 5 MB × 3). API keys aur
passwords kabhi log nahi hote.

**Error pages**: custom `400/403/404/500` templates wired hain
(`config/urls.py` → `core.views.*`), taaki unexpected errors par bhi clean page dikhe.

---

## Production deployment

1. `.env` me `KAAMSETU_DEBUG=false`, strong `KAAMSETU_SECRET_KEY`,
   `KAAMSETU_ALLOWED_HOSTS`, `KAAMSETU_CSRF_TRUSTED_ORIGINS` set karo.
2. `python manage.py collectstatic` (static ko web server / CDN se serve karo;
   media ko object storage ya alag volume par rakho).
3. `python manage.py migrate`.
4. Django dev server **production me mat chalao** — WSGI/ASGI server use karo
   (jaise `gunicorn config.wsgi:application` ya `uvicorn config.asgi:application`)
   ek reverse proxy (Nginx/Caddy) ke peeche, jo HTTPS, static/media aur
   upload size limits handle kare.
5. Bade scale par SQLite concurrent writes ke liye theek nahi — PostgreSQL par
   switch karo (models pehle se Postgres-compatible hain).
6. AI video analysis request ke andar chalti hai; heavy load par ise background
   worker (queue) me move karna chahiye.

> Ye project abhi **dev-verified** hai (offline tests + `manage.py check`), lekin
> load-tested ya "unlimited scale" nahi. Production claim karne se pehle apne
> environment par load test aur security review zaroor karo.

---

## Apps & routes

| App         | Responsibility | Key URLs |
|-------------|----------------|----------|
| `core`      | Landing, About, How It Works, Terms/Privacy, language switch | `/`, `/home/`, `/about/`, `/how-it-works/`, `/select-role/`, `/go/`, `/i18n/set-language/` |
| `accounts`  | Custom user, email login, register, logout | `/accounts/login/`, `/accounts/register/`, `/accounts/logout/` |
| `workers`   | Worker dashboard, profile, skill video, skill analysis, jobs, applications, notifications, settings | `/worker/dashboard/`, `/worker/profile/`, `/worker/video/`, `/worker/skills/`, `/worker/jobs/`, `/worker/applications/`, `/worker/notifications/`, `/worker/settings/` |
| `employers` | Employer dashboard, post/edit/close job, find workers, applications, hired, follow-up, notifications, settings | `/employer/dashboard/`, `/employer/jobs/new/`, `/employer/jobs/`, `/employer/workers/`, `/employer/applications/`, `/employer/hired/`, `/employer/feedback/`, `/employer/notifications/`, `/employer/settings/` |
| `jobs`      | Job model, detail page, applications, saved jobs | `/jobs/new/`, `/jobs/<id>/` |
| `hiring`    | Consent-gated hiring pipeline (interest → consent → connection → follow-up) | `/hiring/...` |
| `agents`    | Rule-based agent helpers (listing verification, listing parsing, matching, follow-up scheduling) | — |

Role-aware redirects: login ke baad `/go/` role ke hisaab se worker/employer
dashboard par bhejta hai. Protected views `core.decorators.role_required`
(worker/employer) se guarded hain; unauthorised users login par redirect hote hain.

---

## Localization (24 Indian languages)

- Custom lightweight i18n layer: `core/i18n.py` (English strings hi keys hain).
- Template tags/filters: `core/templatetags/ks_i18n.py` → `{% t "Key" %}` aur `{{ value|tr }}`.
- Switcher (navbar) me **24 languages** hain: English + 22 scheduled Indian
  languages (हिन्दी, मराठी, বাংলা, தமிழ், తెలుగు, ગુજરાતી, ಕನ್ನಡ, മലയാളം, ਪੰਜਾਬੀ,
  ଓଡ଼ିଆ, অসমীয়া, اردو, नेपाली, मैथिली, कोंकणी, डोगरी, संस्कृतम्, سنڌي, کٲشُر,
  মৈতৈলোন্, बड़ो, ᱥᱟᱱᱛᱟᱲᱤ) + भोजपुरी.
- **RTL support**: Urdu / Sindhi / Kashmiri chunne par `base.html` ka
  `<html dir="rtl">` ho jaata hai (baaki sab `ltr`).
- **Fallback chain**: jis language ki abhi dictionary nahi hai wo apni nazdeeki
  language se translate hoti hai (jaise `mai`/`doi`/`sa` → `hi`, `kok` → `mr`,
  `sd`/`ks` → `ur`, `mni` → `bn`, `brx` → `as`), aur uske baad English.
- Language choice session (`ks_language`) + cookie me save hoti hai, isliye pages ke
  beech persist karti hai. Navbar ka language picker `core:set_language` par POST karta hai.
- Nav, buttons, form labels, statuses aur user-facing messages translated hain.

Naya string add karne ke liye `core/i18n.py` ke `TRANSLATIONS['hi']` / `['mr']`
dict me entry daalo (English string as key). Missing key fallback me English hi dikhega.

---

## Email (employer -> worker)

Employer **Find Workers / Worker detail** page par worker ke **Call** button ke
niche **Send mail** button hai. Click karne par Gmail compose khulta hai —
desktop par naya tab, mobile par Gmail app — aur worker ka address **To** me
pehle se bhara hota hai. Employer sirf subject aur message likh kar send karta
hai, isliye mail uske **apne** Gmail account se jaati hai.

Iske liye app me koi SMTP / app-password setup karne ki zaroorat nahi hai
(`https://mail.google.com/mail/?view=cm&fs=1&to=...` deep link use hota hai).

- **Dev SMTP (optional)**: agar app khud background me mail bheje (jaise
  `sendtestemail`), to project root me `.env` banao — `.env.example` ko copy
  karke details bharo. Django isse automatically load karta hai
  (`config/settings.py`), koi extra package nahi chahiye:

```ini
KAAMSETU_EMAIL_HOST=smtp.gmail.com
KAAMSETU_EMAIL_PORT=587
KAAMSETU_EMAIL_HOST_USER=you@gmail.com
KAAMSETU_EMAIL_HOST_PASSWORD=your-16-char-app-password
KAAMSETU_DEFAULT_FROM_EMAIL=KaamSetu <you@gmail.com>
KAAMSETU_EMAIL_USE_TLS=true
```

  Gmail ke liye 2-Step Verification on karke **App password** banayein (normal
  password kaam nahi karega). Outlook ke liye `smtp.office365.com` use karein.
  SMTP set na hone par mail `BASE_DIR/sent_emails/` me file ke roop me likhi
  jaati hai.
- **Verify**: `.env` set karne ke baad test mail bhejo —

```powershell
python manage.py sendtestemail you@gmail.com
```

---

## Vision AI (video se skill detection)

Worker jab **AI Skill Analyzer** me video upload karta hai aur koi skill select
nahi karta, to video sach me ek vision model ko bheji jaati hai (Google Gemini).
Model video dekh kar batata hai: **skill kya hai**, **level** (beginner /
working / skilled) aur ek chhota English explanation. Wahi skill worker ke
profile me add ho jaati hai (`WorkerSkill`, source = AI, verified = True).

- Code: `agents/vision.py` (`analyze()`), report: `agents/logic.py::assess_skill_video()`.
- Sirf standard library (`urllib`) use hoti hai — koi extra package nahi.
  15 MB tak video inline jaati hai, usse badi File API se upload hoti hai.
- **Key set karna**: `.env` me `KAAMSETU_GEMINI_API_KEY` daalo (free key —
  https://aistudio.google.com/apikey), phir server restart. Model badalna ho to
  `KAAMSETU_GEMINI_MODEL` set karo (default `gemini-2.5-flash`).
- **Key na ho to** app waise hi chalta rahega: skill video ke file name se
  detect hoti hai (jaise `cooking.mp4` -> Cook) aur report rule-based banti hai.
  Agar worker khud skill select kar le, to AI call hi nahi hoti.

## AI Help Assistant

The site-wide worker/employer help chat uses the Gemini API model
`gemini-3.5-flash-lite` when `KAAMSETU_GEMINI_API_KEY` is configured. It sends
the current question, up to three recent message pairs, role, and interface
language; KaamSetu does not store chat text. The API free tier has changing usage limits, and Google may
use free-tier prompts to improve its products. The help panel warns users not
to share passwords, OTPs, or private details. If no key is set or Gemini is
unavailable, the local FAQ answers common questions and directs unresolved
issues to support.

- Get a key in [Google AI Studio](https://aistudio.google.com/apikey).
- Set `KAAMSETU_GEMINI_API_KEY` in local `.env` or as a secret environment
  variable in Render. Never commit the key or paste it into browser code.
- The default model can be changed with `KAAMSETU_CHATBOT_MODEL`.
- Requests are limited per client IP and questions are capped at 600 characters.

---

## Feature checklist

**Public**: landing (hero, about/mission, how-it-works steps, feature cards,
final CTA, footer), role selection, register (full name, email, mobile,
role, password + confirm, terms), login (email/password, remember me, role-aware
redirect), 404.

**Worker**: dashboard (welcome, profile completion %, recommended jobs, notifications,
quick links), profile create/edit (personal, location, education, work preferences),
skill video upload (**koi bhi file type/extension**, size validation, preview, real
media save), AI skill analysis
(Gemini video + speech analysis when a key is set), recommended jobs (search, filters, sort by match,
save/unsave, apply once), My Applications (status filters), notifications, settings
(job alerts, nearby-only, visibility, preferred job type, min salary).

**Employer**: dashboard (jobs/applications/hired summary, recent applications, quick
actions), post a job (validation + rule-based safety check for fees/deposits/OTP/
passwords, labelled rule-based), My Jobs (own jobs, applicant counts, edit/close),
find workers (search by name/skill/location, match score, respects visibility),
worker details (permitted details + **click-to-call `tel:`** + in-app email),
applications (applicant summary, status change: Applied/Shortlisted/Rejected/Hired),
hired workers (Day 7/30/90 milestones), feedback (milestone + rating 1–5 + notes),
notifications, settings.

Jahan bhi worker list hoti hai (Find Workers, Applications, Hired), wahan
`tel:` **click-to-call** link hota hai. Consent-gated **hiring** pipeline
(`hiring` app) worker ke approve kiye fields hi employer ko dikhata hai.

**Hired-worker privacy**: jab kisi worker ko koi employer hire kar leta hai, to
us worker ka naam/profile **baaki employers** ki Find Workers list aur worker
detail page se chhup jaata hai (jisne hire kiya, use dikhta rehta hai). Isse
hired worker dobara poach nahi hota.

**Data models**: custom `User` (role + contact), `WorkerProfile` + `WorkerSkill`,
`EmployerProfile`, `Job`, `SavedJob`, `JobApplication` (unique worker/job),
`Notification`, `Feedback` (unique application/milestone), `SkillAssessment` (video
media record), plus `hiring` models (Consent/Connection/JobInterest).

---

## Notes on reference reproduction

- **Visual parity**: React ke CSS modules port kiye gaye (`theme`, `components`,
  `pages`, `images`, `visual-polish`, `django`, `forms`) — white + lavender theme,
  cards, navbar, footer, dashboard sidebars, badges, empty states, responsive grids.
  Existing images aur `static/images/` ka brand logo reuse kiya gaya hai.
- **Lucide icons** React ki tarah CDN se load hote hain aur `data-lucide="..."` se render.
- **AI features**: skill video analysis real vision AI (Google Gemini) se hoti
  hai — key set hone par video + speech dono analyse hote hain. Job matching aur
  listing verification deterministic **rule-based** logic se reproduce kiye gaye
  hain (`agents/logic.py`, `core/matching.py`), kyunki wo transparent aur
  audit-friendly rehne chahiye.
- **Safety check**: job listing verification simple keyword rules par based hai
  (registration fee, deposit, OTP, password) — AI claim nahi karta.
- Browser `localStorage` database ke roop me use **nahi** hua; sab kuch server-side
  models me persist hota hai.
