from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from agents.logic import verify_listing
from core.decorators import employer_required
from core.matching import get_match_score
from core.models import Notification
from jobs.models import Job, JobApplication, JobVerification
from workers.models import DetectedSkill, WorkerProfile

from .forms import EmployerSettingsForm, FeedbackForm, JobForm
from .models import EmployerProfile, Feedback


def get_profile(user):
    return EmployerProfile.objects.get_or_create(
        user=user, defaults={'business_name': user.display_name}
    )[0]


def _own_jobs(profile):
    return Job.objects.filter(employer=profile).select_related('area', 'skill')


def _own_applications(profile):
    return (
        JobApplication.objects.filter(job__employer=profile)
        .select_related('job', 'job__employer', 'worker', 'worker__area')
    )


def _hired_by_others(profile):
    """In worker ids ko is employer ko nahi dikhana hai.

    Kyunki un worker ko kisi doosre employer ne hire kar liya hai — privacy
    ke liye unka naam/profile baaki employers se chhupa rehta hai.
    """
    return set(
        JobApplication.objects.filter(status=JobApplication.Status.HIRED)
        .exclude(job__employer=profile)
        .values_list('worker_id', flat=True)
    )


@employer_required
def dashboard(request):
    profile = get_profile(request.user)
    jobs = _own_jobs(profile)
    open_jobs = jobs.filter(status=Job.Status.ACTIVE)
    applications = _own_applications(profile)

    workers = (
        WorkerProfile.objects.filter(profile_visible=True)
        .exclude(pk__in=_hired_by_others(profile))
        .select_related('area')
    )
    if open_jobs.exists():
        ranked = sorted(
            (
                (worker, max(get_match_score(worker, job) for job in open_jobs))
                for worker in workers
            ),
            key=lambda pair: pair[1], reverse=True,
        )
    else:
        ranked = []
    matched_workers_count = sum(1 for _worker, score in ranked if score > 0)
    ranked = ranked[:2]
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

    return render(request, 'employers/dashboard.html', {
        'profile': profile,
        'jobs': jobs,
        'applications': applications,
        'recent_applications': applications[:3],
        'active_jobs': jobs.filter(status=Job.Status.ACTIVE).count(),
        'hired_count': applications.filter(status=JobApplication.Status.HIRED).count(),
        'matched_workers_count': matched_workers_count,
        'application_pipeline': application_pipeline,
        'ranked_workers': [{'worker': worker, 'match': score} for worker, score in ranked],
    })


@employer_required
def post_job(request):
    profile = get_profile(request.user)
    form = JobForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        job = form.save(commit=False)
        job.employer = profile
        job.status = Job.Status.ACTIVE
        job.created_via = 'web'
        job.save()
        # Rule-based listing safety check.
        result = verify_listing(f'{job.title} {job.description}', {
            'wage_max': job.wage_max, 'wage_period': job.wage_period,
            'skill_name': (job.required_skills or [''])[0],
        })
        JobVerification.objects.update_or_create(
            job=job,
            defaults={
                'status': JobVerification.Status.PASSED if result['status'] == 'passed' else JobVerification.Status.FLAGGED,
                'risk_score': result['risk_score'], 'flags': result['flags'], 'summary': result['summary'],
            },
        )
        messages.success(request, 'Job verified and published. Matching workers can now see it.')
        return redirect('employers:jobs')
    return render(request, 'employers/post_job.html', {'form': form, 'profile': profile})


@employer_required
def jobs(request):
    profile = get_profile(request.user)
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    ordering = request.GET.get('sort', 'newest')
    if ordering not in ('newest', 'oldest', 'status'):
        ordering = 'newest'

    queryset = _own_jobs(profile).annotate(
        applicant_count=Count('applications', distinct=True),
        pending_count=Count(
            'applications', filter=Q(applications__status__in=(
                JobApplication.Status.APPLIED, JobApplication.Status.UNDER_REVIEW,
            )), distinct=True,
        ),
        shortlisted_count=Count(
            'applications', filter=Q(applications__status=JobApplication.Status.SHORTLISTED),
            distinct=True,
        ),
    )
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
            | Q(location__icontains=query) | Q(company_name__icontains=query)
        )
    valid_statuses = {choice for choice, _label in Job.Status.choices}
    if status in valid_statuses:
        queryset = queryset.filter(status=status)
    else:
        status = ''
    order_by = {'newest': '-created_at', 'oldest': 'created_at', 'status': 'status'}[ordering]
    if ordering == 'status':
        queryset = queryset.order_by('status', '-created_at')
    else:
        queryset = queryset.order_by(order_by)
    total = queryset.count()
    page = Paginator(queryset, 8).get_page(request.GET.get('page'))
    return render(request, 'employers/jobs.html', {
        'profile': profile, 'results': page, 'total': total, 'query': query,
        'active_status': status, 'sort': ordering, 'job_statuses': Job.Status.choices,
    })


@employer_required
def job_detail(request, job_id):
    profile = get_profile(request.user)
    job = get_object_or_404(
        _own_jobs(profile).annotate(
            applicant_count=Count('applications', distinct=True),
            pending_count=Count('applications', filter=Q(applications__status__in=(
                JobApplication.Status.APPLIED, JobApplication.Status.UNDER_REVIEW,
            )), distinct=True),
            shortlisted_count=Count('applications', filter=Q(
                applications__status=JobApplication.Status.SHORTLISTED,
            ), distinct=True),
        ), pk=job_id,
    )
    return render(request, 'employers/job_detail.html', {'profile': profile, 'job': job})


@employer_required
def edit_job(request, job_id):
    profile = get_profile(request.user)
    job = get_object_or_404(Job, pk=job_id, employer=profile)
    form = JobForm(request.POST or None, instance=job)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Job updated.')
        return redirect('employers:jobs')
    return render(request, 'employers/post_job.html', {'form': form, 'profile': profile, 'job': job})


@employer_required
@require_POST
def close_job(request, job_id):
    profile = get_profile(request.user)
    job = get_object_or_404(Job, pk=job_id, employer=profile)
    job.status = Job.Status.CLOSED
    job.save(update_fields=['status'])
    messages.success(request, 'Job closed.')
    return redirect('employers:jobs')


@employer_required
def workers(request):
    profile = get_profile(request.user)
    query = request.GET.get('q', '').strip()
    queryset = (
        WorkerProfile.objects.filter(profile_visible=True)
        .exclude(pk__in=_hired_by_others(profile))
        .select_related('area')
    )
    if query:
        queryset = queryset.filter(
            Q(full_name__icontains=query) | Q(village__icontains=query)
            | Q(district__icontains=query) | Q(preferred_job__icontains=query)
            | Q(skills__skill__name__icontains=query)
        ).distinct()

    own_jobs = list(_own_jobs(profile))
    cards = []
    for worker in queryset:
        score = max((get_match_score(worker, job) for job in own_jobs), default=0)
        cards.append({'worker': worker, 'match': score})
    cards.sort(key=lambda c: c['match'], reverse=True)
    page = Paginator(cards, 9).get_page(request.GET.get('page'))
    return render(request, 'employers/workers.html', {'profile': profile, 'results': page, 'total': len(cards), 'query': query})


@employer_required
def worker_detail(request, worker_id):
    profile = get_profile(request.user)
    worker = get_object_or_404(WorkerProfile, pk=worker_id)
    if worker.id in _hired_by_others(profile):
        messages.error(request, 'This worker has already been hired, so their profile is no longer listed.')
        return redirect('employers:workers')
    if not worker.profile_visible and not worker.applications.filter(job__employer=profile).exists():
        messages.error(request, 'This worker has hidden their profile from employers.')
        return redirect('employers:workers')
    own_jobs = list(_own_jobs(profile))
    match = max((get_match_score(worker, job) for job in own_jobs), default=0)
    from hiring.models import ConsentGrant
    consent = ConsentGrant.objects.filter(
        interest__worker=worker, interest__job__employer=profile, is_active=True
    ).select_related('interest').first()
    shared_assessment = worker.assessments.first() if consent and consent.share_video else None
    return render(request, 'employers/worker_detail.html', {
        'profile': profile, 'worker': worker, 'match': match,
        'consent': consent,
        'shared_assessment': shared_assessment,
        'skills': worker.skills.select_related('skill'),
        'ai_skills': _accepted_ai_skills(worker),
    })


def _accepted_ai_skills(worker):
    """Only the skills the worker *accepted* from an AI assessment.

    Rejected (and still pending) detections are never exposed to employers,
    and neither are skills that were accepted without real visual evidence —
    those carry no rating and are not on the public profile either. For skills
    seen in several videos the most recent accepted assessment is shown.
    """
    accepted = (
        DetectedSkill.objects
        .filter(
            worker=worker,
            approval_status=DetectedSkill.Approval.ACCEPTED,
            evidence_status__in=DetectedSkill.ASSESSABLE,
            score__isnull=False,
        )
        .select_related('assessment')
        .order_by('-created_at')
    )
    latest = {}
    for detected in accepted:
        latest.setdefault(detected.name.lower(), detected)
    return list(latest.values())


@employer_required
def applications(request):
    profile = get_profile(request.user)
    queryset = _own_applications(profile)
    job_id = request.GET.get('job', '').strip()
    selected_job = None
    if job_id.isdigit():
        selected_job = _own_jobs(profile).filter(pk=job_id).first()
        if selected_job:
            queryset = queryset.filter(job=selected_job)
    all_count = queryset.count()
    active = request.GET.get('status', 'All')
    if active and active != 'All':
        queryset = queryset.filter(status=active)
    total = queryset.count()
    page = Paginator(queryset, 9).get_page(request.GET.get('page'))
    return render(request, 'employers/applications.html', {
        'profile': profile, 'results': page,
        'total': total,
        'all_count': all_count,
        'statuses': list(JobApplication.Status.values),
        'active_status': active or 'All',
        'selected_job': selected_job,
        'filter_jobs': _own_jobs(profile),
        'update_statuses': [status for status in JobApplication.Status.values if status != JobApplication.Status.HIRED],
    })


@employer_required
@require_POST
def update_application_status(request, application_id):
    profile = get_profile(request.user)
    application = get_object_or_404(JobApplication, pk=application_id, job__employer=profile)
    status = request.POST.get('status')
    if status in JobApplication.Status.values:
        if status == JobApplication.Status.HIRED:
            messages.error(request, 'Confirm hiring from the consent-approved candidate connection.')
            target = request.POST.get('next')
            if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
                return redirect(target)
            return redirect('employers:applications')
        application.status = status
        application.save(update_fields=['status', 'updated_at'])
        Notification.objects.create(
            user=application.worker.user,
            title=f'{application.job.title}: {status}',
            body=f'{application.job.company_label} updated your application.',
            url='/worker/applications/',
        )
        messages.success(request, f'Application marked as {status}.')
    else:
        messages.error(request, 'Unknown application status.')
    target = request.POST.get('next')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect('employers:applications')


@employer_required
def hired(request):
    profile = get_profile(request.user)
    # prefetch_related avoids one feedback query per hired application (N+1).
    hired_apps = (
        _own_applications(profile)
        .filter(status=JobApplication.Status.HIRED)
        .prefetch_related('feedback')
    )
    rows = []
    for application in hired_apps:
        done = {fb.milestone for fb in application.feedback.all()}
        rows.append({
            'application': application,
            'done': done,
            'next': next((day for day in (7, 30, 90) if day not in done), None),
        })
    return render(request, 'employers/hired.html', {'profile': profile, 'rows': rows, 'total': len(rows)})


@employer_required
def feedback(request):
    profile = get_profile(request.user)
    application_id = request.GET.get('application') or request.POST.get('application')
    application = None
    if application_id:
        application = get_object_or_404(JobApplication, pk=application_id, job__employer=profile)
    day = request.GET.get('day')
    initial = {'milestone': int(day)} if day in ('7', '30', '90') else {}
    form = FeedbackForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        record = form.save(commit=False)
        if application is None:
            messages.error(request, 'Open follow-up from a hired worker’s application.')
            return redirect('employers:hired')
        record.application = application
        record.save()
        messages.success(request, 'Follow-up saved.')
        return redirect('employers:hired')
    hired_applications = (
        _own_applications(profile).filter(status=JobApplication.Status.HIRED)
        if application is None else None
    )
    return render(request, 'employers/feedback.html', {
        'profile': profile, 'form': form, 'application': application,
        'hired_applications': hired_applications,
    })


@employer_required
def notifications(request):
    notes = request.user.notifications.all()
    page = Paginator(notes, 15).get_page(request.GET.get('page'))
    return render(request, 'employers/notifications.html', {'notifications': page, 'total': notes.count()})


@employer_required
def settings(request):
    profile = get_profile(request.user)
    form = EmployerSettingsForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Preferences saved.')
        return redirect('employers:settings')
    return render(request, 'employers/settings.html', {'form': form, 'profile': profile})
