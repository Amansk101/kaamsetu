from django.contrib import messages
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from agents import vision as vision_ai
from agents.logic import assess_skill_video
from agents.models import AgentLog
from core.decorators import worker_required
from core.matching import get_match_score
from core.models import Notification, Skill
from jobs.models import Job, JobApplication, SavedJob

from .forms import SkillVideoForm, WorkerProfileForm, WorkerSettingsForm
from .models import DetectedSkill, SkillAssessment, WorkerProfile, WorkerSkill

# Per-skill demo score used on the rule-based analysis page.
_LEVEL_SCORE = {'beginner': 55, 'working': 72, 'skilled': 88}


def get_profile(user):
    return WorkerProfile.objects.get_or_create(
        user=user, defaults={'full_name': user.display_name, 'mobile': user.phone or '', 'email': user.email}
    )[0]


def _store_detected_skills(assessment, report):
    """Persist every skill the AI discovered as its own pending DetectedSkill row.

    Nothing is added to the worker's public profile here — the worker reviews
    each row and accepts the ones that really are their work.
    """
    rows = []
    for item in report.get('skills') or []:
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        rows.append(DetectedSkill(
            assessment=assessment,
            worker=assessment.worker,
            name=name,
            description=str(item.get('description') or ''),
            category=str(item.get('category') or ''),
            score=item.get('score'),
            level=str(item.get('level') or ''),
            confidence=item.get('confidence'),
            reason=str(item.get('reason') or ''),
            strengths=list(item.get('strengths') or []),
            improvements=list(item.get('improvements') or []),
            recommendations=list(item.get('recommendations') or []),
            evidence=list(item.get('evidence') or []),
            limitations=str(item.get('limitations') or ''),
            evidence_status=item.get('evidence_status') or DetectedSkill.Evidence.INSUFFICIENT,
            approval_status=DetectedSkill.Approval.PENDING,
        ))
    if rows:
        DetectedSkill.objects.bulk_create(rows)
    return rows


def _accept_detected_skill(detected):
    """Accept one detected skill: expose it on the public profile."""
    detected.approval_status = DetectedSkill.Approval.ACCEPTED
    detected.save(update_fields=['approval_status', 'updated_at'])
    if detected.is_assessable:
        skill, _ = Skill.objects.get_or_create(name=detected.name)
        detected.skill = skill
        detected.save(update_fields=['skill', 'updated_at'])
        WorkerSkill.objects.update_or_create(
            worker=detected.worker, skill=skill,
            defaults={
                'level': detected.profile_level,
                'confidence': detected.confidence,
                'verified': True,
                'source': WorkerSkill.Source.AI,
            },
        )
        return True
    return False


def _revoke_detected_skill(detected):
    """Reject / un-accept a detected skill and pull it off the public profile."""
    detected.approval_status = DetectedSkill.Approval.REJECTED
    detected.save(update_fields=['approval_status', 'updated_at'])
    if detected.skill_id:
        WorkerSkill.objects.filter(worker=detected.worker, skill_id=detected.skill_id).delete()


def _safe_next(request, fallback):
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _skill_score(worker_skill):
    """Rule-based 0–100 score from the worker's level and AI confidence."""
    score = _LEVEL_SCORE.get(worker_skill.level, 60)
    if worker_skill.confidence:
        score = round(score * 0.5 + float(worker_skill.confidence) * 100 * 0.5)
    return max(0, min(99, score))


@worker_required
def dashboard(request):
    profile = get_profile(request.user)
    skills = list(profile.skills.select_related('skill'))
    applications = JobApplication.objects.filter(worker=profile).select_related('job', 'job__employer')

    jobs = Job.objects.filter(status=Job.Status.ACTIVE).select_related('employer', 'area')
    job_matches = list((job, get_match_score(profile, job)) for job in jobs)
    recommended = sorted(
        job_matches,
        key=lambda pair: pair[1], reverse=True,
    )[:2]
    applied_ids = set(applications.values_list('job_id', flat=True))
    application_total = applications.count()
    application_counts = dict(
        applications.values('status').annotate(total=Count('pk')).values_list('status', 'total')
    )
    application_pipeline = [
        {'label': label, 'count': application_counts.get(status, 0),
         'share': round(application_counts.get(status, 0) * 100 / application_total) if application_total else 0}
        for status, label in JobApplication.Status.choices
        if application_counts.get(status, 0)
    ]
    return render(request, 'workers/dashboard.html', {
        'dashboard_video': bool(finders.find('videos/kaamsetu-worker-dashboard.mp4')),
        'profile': profile,
        'skills': skills,
        'applications': applications,
        'recommended': [
            {'job': job, 'match': score, 'applied': job.id in applied_ids}
            for job, score in recommended
        ],
        'matched_jobs_count': sum(1 for _job, score in job_matches if score > 0),
        'application_pipeline': application_pipeline,
        'shortlisted_count': applications.filter(
            status__in=['Shortlisted', 'Interview', 'Selected', 'Hired']
        ).count(),
        'notifications': request.user.notifications.all()[:3],
    })


@worker_required
def profile_view(request):
    profile = get_profile(request.user)
    form = WorkerProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save()
        profile.profile_completed = profile.profile_completion >= 80
        profile.save(update_fields=['profile_completed'])
        messages.success(request, 'Your profile has been updated.')
        return redirect('workers:profile')
    return render(request, 'workers/profile.html', {
        'form': form,
        'profile': profile,
        'skills': profile.skills.select_related('skill'),
    })


@worker_required
def upload_video(request):
    profile = get_profile(request.user)
    form = SkillVideoForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        assessment = form.save(commit=False)
        assessment.worker = profile
        if not assessment.duration_seconds:
            assessment.duration_seconds = max(5, min(90, assessment.video.size // 100000))

        # The worker is never forced to pick a skill — the video is sent to the
        # vision AI model (when a key is set) and it discovers the profession and
        # every skill it actually sees and hears.
        vision = None
        ai_enabled = vision_ai.is_enabled()
        if ai_enabled:
            vision = vision_ai.analyze(
                assessment.video,
                allowed_skills=list(Skill.objects.values_list('name', flat=True)),
            )
            if vision is None:
                messages.warning(
                    request,
                    'The AI video analysis could not run (check the Gemini key, quota and internet). '
                    'A rule-based report is shown instead — no skill scores were given.',
                )

        existing = profile.skills.first()
        result = assess_skill_video(
            assessment.duration_seconds,
            existing.level if existing else 'beginner',
            '',
            filename=assessment.video.name,
            vision=vision,
        )
        assessment.transcript = str((vision or {}).get('transcript') or '')
        assessment.ai_notes = result['notes']
        assessment.ai_report = result
        assessment.final_level = result['level'] if result['level'] in ('beginner', 'working', 'skilled') else ''
        assessment.ai_level = assessment.final_level
        assessment.ai_confidence = result['confidence'] or None
        assessment.detected_profession = result.get('profession') or ''
        assessment.profession_confidence = result.get('profession_confidence') or None
        assessment.work_summary = result.get('work_summary') or ''
        assessment.analysis_source = (
            SkillAssessment.Source.AI if result.get('is_ai') else SkillAssessment.Source.RULE_BASED
        )
        assessment.ai_provider = result.get('provider') or ''
        assessment.ai_model = result.get('model') or ''
        assessment.status = SkillAssessment.Status.COMPLETED
        assessment.save()

        # Every discovered skill is stored separately as *pending* — the worker
        # decides which ones go on their public profile.
        _store_detected_skills(assessment, result)
        profile.verified = True
        profile.save(update_fields=['verified'])

        pending = assessment.detected_skills.count()
        if pending:
            count = result.get('assessable_count') or 0
            messages.success(
                request,
                f'Video analysed. The AI found {pending} skill(s); {count} could be rated from '
                f'the evidence. Review them and accept the ones that are really your work.',
            )
        else:
            messages.warning(
                request,
                'The video was analysed but no specific skill could be identified. '
                'Record a longer, clearer demonstration and try again.',
            )
        return redirect('workers:assessment_detail', assessment_id=assessment.pk)
    return render(request, 'workers/upload_video.html', {
        'form': form,
        'profile': profile,
        'assessments': profile.assessments.all()[:5],
        'ai_enabled': vision_ai.is_enabled(),
    })


@worker_required
@require_POST
def delete_assessment(request, assessment_id):
    """Delete an uploaded skill video and its analysis file."""
    profile = get_profile(request.user)
    assessment = get_object_or_404(SkillAssessment, pk=assessment_id, worker=profile)
    if assessment.video:
        assessment.video.delete(save=False)
    assessment.delete()
    messages.success(request, 'Your skill video was deleted.')
    return redirect(_safe_next(request, 'workers:upload_video'))


@worker_required
def skill_analysis(request):
    """Overview: the worker's accepted skills + every past assessment."""
    profile = get_profile(request.user)
    skills = list(profile.skills.select_related('skill'))
    cards = [
        {'id': ws.pk, 'name': ws.skill.name, 'level': ws.get_level_display(), 'score': _skill_score(ws)}
        for ws in skills
    ]
    overall = round(sum(card['score'] for card in cards) / len(cards)) if cards else 0

    assessments = list(
        profile.assessments.prefetch_related('detected_skills')[:20]
    )
    latest = assessments[0] if assessments else None
    pending = DetectedSkill.objects.filter(
        worker=profile, approval_status=DetectedSkill.Approval.PENDING
    ).select_related('assessment')
    if latest and latest.ai_report:
        overall = latest.ai_report.get('overall', overall)

    return render(request, 'workers/skill_analysis.html', {
        'profile': profile,
        'cards': cards,
        'overall': overall,
        'assessments': assessments,
        'latest': latest,
        'pending_count': pending.count(),
        'ai_enabled': vision_ai.is_enabled(),
        'ai_error': _last_ai_error(latest),
    })


def _last_ai_error(assessment):
    """Surface the most recent vision failure so the worker knows why."""
    if assessment and (assessment.ai_report or {}).get('is_ai'):
        return ''
    if not vision_ai.is_enabled():
        return ''
    last = AgentLog.objects.filter(agent='SkillVisionAgent').first()
    if last and 'failed' in (last.input_summary or '').lower():
        return last.input_summary
    return ''


@worker_required
def assessment_detail(request, assessment_id):
    """One assessment: the profession, every detected skill and approval controls."""
    profile = get_profile(request.user)
    assessment = get_object_or_404(
        SkillAssessment, pk=assessment_id, worker=profile
    )
    return render(request, 'workers/assessment_detail.html', {
        'profile': profile,
        'assessment': assessment,
        'report': assessment.ai_report or None,
        'detected': assessment.detected_skills.all(),
        'ai_enabled': vision_ai.is_enabled(),
    })


@worker_required
@require_POST
def decide_skill(request, skill_id, decision):
    """Accept or reject one detected skill (POST only)."""
    profile = get_profile(request.user)
    detected = get_object_or_404(DetectedSkill, pk=skill_id, worker=profile)
    if decision == 'accept':
        exposed = _accept_detected_skill(detected)
        if exposed:
            messages.success(
                request,
                f'“{detected.name}” was added to your profile and is now visible to employers.',
            )
        else:
            messages.info(
                request,
                f'“{detected.name}” was accepted, but no score can be shown because the video '
                f'did not give enough evidence. It will not appear in employer matches.',
            )
    elif decision == 'reject':
        _revoke_detected_skill(detected)
        messages.success(request, f'“{detected.name}” was rejected and removed from your profile.')
    else:
        messages.error(request, 'Unknown action.')
    return redirect(_safe_next(request, reverse('workers:assessment_detail', args=[detected.assessment_id])))


@worker_required
@require_POST
def accept_all_skills(request, assessment_id):
    """Accept every detected skill of one assessment that has real evidence."""
    profile = get_profile(request.user)
    assessment = get_object_or_404(SkillAssessment, pk=assessment_id, worker=profile)
    accepted = 0
    for detected in assessment.detected_skills.filter(
        approval_status=DetectedSkill.Approval.PENDING
    ):
        if detected.is_assessable and _accept_detected_skill(detected):
            accepted += 1
        else:
            messages.info(
                request,
                f'“{detected.name}” was skipped — there was not enough visual evidence to rate it.',
            )
    if accepted:
        messages.success(request, f'{accepted} skill(s) added to your profile.')
    return redirect(_safe_next(request, reverse('workers:assessment_detail', args=[assessment.pk])))


@worker_required
@require_POST
def delete_skill(request, skill_id):
    """Remove one skill from the worker's profile.

    Skills are added either by hand or from an analysed video, and this lets the
    worker take any of them back off their profile.
    """
    profile = get_profile(request.user)
    worker_skill = get_object_or_404(WorkerSkill, pk=skill_id, worker=profile)
    name = worker_skill.skill.name
    worker_skill.delete()
    messages.success(request, f'“{name}” was removed from your skills.')
    return redirect(_safe_next(request, 'workers:skill_analysis'))


@worker_required
def jobs(request):
    profile = get_profile(request.user)
    search = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()
    job_type = request.GET.get('job_type', '').strip()
    min_salary = request.GET.get('min_salary', '').strip()

    queryset = Job.objects.filter(status=Job.Status.ACTIVE).select_related('employer', 'area')
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(company_name__icontains=search)
            | Q(employer__business_name__icontains=search) | Q(raw_description__icontains=search)
        )
    if location:
        queryset = queryset.filter(Q(location__icontains=location) | Q(area__name__icontains=location))
    if job_type:
        queryset = queryset.filter(job_type=job_type)
    if min_salary.isdigit():
        minimum = int(min_salary)
        def monthly_equivalent(job):
            amount = job.wage_max or job.wage_min
            if amount is None:
                return 0
            if job.wage_period == Job.WagePeriod.HOUR:
                return amount * 8 * 26
            if job.wage_period == Job.WagePeriod.DAY:
                return amount * 26
            return amount
        queryset = [job for job in queryset if monthly_equivalent(job) >= minimum]
    else:
        queryset = list(queryset)

    scored = sorted(
        ((job, get_match_score(profile, job)) for job in queryset),
        key=lambda pair: pair[1], reverse=True,
    )
    saved_ids = set(SavedJob.objects.filter(worker=profile).values_list('job_id', flat=True))
    applied_ids = set(
        JobApplication.objects.filter(worker=profile).values_list('job_id', flat=True)
    )

    filter_query = request.GET.copy()
    filter_query.pop('page', None)
    page = Paginator(
        [
            {'job': job, 'match': score, 'applied': job.id in applied_ids, 'saved': job.id in saved_ids}
            for job, score in scored
        ],
        8,
    ).get_page(request.GET.get('page'))
    return render(request, 'workers/jobs.html', {
        'profile': profile,
        'results': page,
        'total': len(scored),
        'saved_ids': saved_ids,
        'applied_ids': applied_ids,
        'filters': {'q': search, 'location': location, 'job_type': job_type, 'min_salary': min_salary},
        'filter_query': filter_query.urlencode(),
        'job_types': Job.JobType.choices,
    })


@worker_required
@require_POST
def apply_job(request, job_id):
    profile = get_profile(request.user)
    job = get_object_or_404(Job, pk=job_id)
    application, created = JobApplication.objects.get_or_create(
        worker=profile, job=job,
        defaults={'match_score': get_match_score(profile, job)},
    )
    if created:
        Notification.objects.create(
            user=job.employer.user,
            title=f'New applicant for {job.title}',
            body=f'{profile.full_name} applied. Review their profile in Applications.',
            url='/employer/applications/',
        )
        messages.success(request, f'Your application for {job.title} was sent to {job.company_label}.')
    else:
        messages.info(request, 'You have already applied for this role.')
    return redirect(_safe_next(request, 'workers:jobs'))


@worker_required
@require_POST
def toggle_save_job(request, job_id):
    profile = get_profile(request.user)
    job = get_object_or_404(Job, pk=job_id)
    saved, created = SavedJob.objects.get_or_create(worker=profile, job=job)
    if not created:
        saved.delete()
        messages.info(request, 'Removed from saved jobs.')
    else:
        messages.success(request, 'Job saved for later.')
    return redirect(_safe_next(request, 'workers:jobs'))


@worker_required
def applications(request):
    profile = get_profile(request.user)
    queryset = JobApplication.objects.filter(worker=profile).select_related('job', 'job__employer')
    statuses = list(JobApplication.Status.values)
    active = request.GET.get('status', 'All')
    filtered = queryset if active in ('All', '') else queryset.filter(status=active)
    page = Paginator(filtered, 10).get_page(request.GET.get('page'))
    return render(request, 'workers/applications.html', {
        'profile': profile,
        'results': page,
        'total': queryset.count(),
        'statuses': statuses,
        'active_status': active or 'All',
    })


@worker_required
@require_POST
def withdraw_application(request, application_id):
    profile = get_profile(request.user)
    application = get_object_or_404(JobApplication, pk=application_id, worker=profile)
    if application.status == JobApplication.Status.APPLIED:
        application.delete()
        messages.success(request, 'Application withdrawn.')
    else:
        messages.error(request, 'Applications can only be withdrawn while they are new.')
    return redirect('workers:applications')


@worker_required
def notifications(request):
    notes = request.user.notifications.all()
    page = Paginator(notes, 15).get_page(request.GET.get('page'))
    return render(request, 'workers/notifications.html', {'notifications': page, 'total': notes.count()})


@worker_required
def settings(request):
    profile = get_profile(request.user)
    form = WorkerSettingsForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Preferences saved.')
        return redirect('workers:settings')
    return render(request, 'workers/settings.html', {'form': form, 'profile': profile})
