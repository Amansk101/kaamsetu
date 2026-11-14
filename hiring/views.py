from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from agents.logic import match_score, schedule_followups
from core.decorators import employer_required, worker_required
from jobs.models import Job, JobApplication
from workers.models import WorkerProfile

from .forms import ConsentForm, FollowUpResponseForm
from .models import Connection, FollowUp, JobInterest


@worker_required
@require_POST
def express_interest(request, job_id):
    profile = getattr(request.user, 'worker_profile', None)
    if profile is None:
        messages.error(request, 'Please complete your worker profile first.')
        return redirect('workers:onboarding')

    job = get_object_or_404(Job, pk=job_id, status=Job.Status.ACTIVE)
    score, reasons = match_score(profile, job)
    interest, created = JobInterest.objects.get_or_create(
        job=job,
        worker=profile,
        defaults={'match_score': score, 'match_reason': '\n'.join(reasons)},
    )
    if not created and interest.status in (JobInterest.Status.DECLINED, JobInterest.Status.WITHDRAWN):
        interest.status = JobInterest.Status.INTERESTED
        interest.save(update_fields=['status'])
    Connection.objects.get_or_create(
        interest=interest,
        defaults={'job': interest.job, 'worker': interest.worker},
    )
    messages.success(request, 'Your interest has been shared with the employer.')
    return redirect('workers:dashboard')


@worker_required
def consent(request, interest_id):
    interest = get_object_or_404(
        JobInterest.objects.select_related('job', 'job__employer'), pk=interest_id,
        worker__user=request.user,
    )
    existing = getattr(interest, 'consent', None)

    if request.method == 'POST':
        if request.POST.get('action') == 'decline':
            if existing:
                existing.is_active = False
                existing.revoked_at = timezone.now()
                existing.save(update_fields=['is_active', 'revoked_at'])
            interest.status = JobInterest.Status.DECLINED
            interest.save(update_fields=['status'])
            messages.info(request, 'You declined to share your details for this opportunity.')
            return redirect('workers:dashboard')
        form = ConsentForm(request.POST, instance=existing)
        if form.is_valid():
            grant = form.save(commit=False)
            grant.interest = interest
            grant.is_active = True
            grant.revoked_at = None
            grant.save()

            interest.status = JobInterest.Status.CONNECTED
            interest.save()

            Connection.objects.get_or_create(
                interest=interest,
                defaults={'job': interest.job, 'worker': interest.worker},
            )
            messages.success(
                request,
                'Consent given. The employer can now see only the details you approved.',
            )
            return redirect('workers:dashboard')
    messages.info(request, 'Profile sharing is managed through the worker profile. Contact links are available on the profile.')
    return redirect('workers:dashboard')


@employer_required
def job_candidates(request, job_id):
    job = get_object_or_404(Job, pk=job_id, employer__user=request.user)
    interests = job.interests.select_related('worker', 'consent', 'connection').all()
    rows = []
    for interest in interests:
        consent = getattr(interest, 'consent', None)
        conn = getattr(interest, 'connection', None)
        has_grant = bool(consent and consent.is_active)
        rows.append({
            'interest': interest,
            'worker': interest.worker,
            'consent': consent,
            'connection': conn,
            'unlocked': interest.status not in (JobInterest.Status.DECLINED, JobInterest.Status.WITHDRAWN, JobInterest.Status.CLOSED),
            'share_name': consent.share_name if has_grant else True,
            'share_city': consent.share_city if has_grant else True,
            'share_skills': consent.share_skills if has_grant else True,
            'share_education': consent.share_education if has_grant else False,
            'share_video': consent.share_video if has_grant else False,
        })
    return render(request, 'hiring/job_candidates.html', {'job': job, 'rows': rows})


@employer_required
@require_POST
def connection_update(request, pk):
    conn = get_object_or_404(Connection, pk=pk, job__employer__user=request.user)
    status = request.POST.get('status')
    if status in dict(Connection.Status.choices):
        conn.status = status
        if status == Connection.Status.HIRED:
            conn.hired_at = timezone.now()
        conn.employer_notes = request.POST.get('notes', conn.employer_notes)
        conn.save()

        if status == Connection.Status.HIRED:
            schedule_followups(conn)
            conn.interest.status = JobInterest.Status.HIRED
            conn.interest.save()
            application, _ = JobApplication.objects.get_or_create(
                job=conn.job, worker=conn.worker,
                defaults={'status': JobApplication.Status.HIRED,
                          'match_score': conn.interest.match_score},
            )
            if application.status != JobApplication.Status.HIRED:
                application.status = JobApplication.Status.HIRED
                application.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Hire confirmed. Follow-ups are now scheduled for day 7, 30 and 90.')
        else:
            messages.info(request, 'Connection status updated.')
    return redirect('hiring:job_candidates', job_id=conn.job_id)


@employer_required
@require_POST
def request_consent(request, worker_id):
    get_object_or_404(Job, pk=request.POST.get('job_id'), employer__user=request.user, status=Job.Status.ACTIVE)
    worker = get_object_or_404(WorkerProfile, pk=worker_id, profile_visible=True)
    messages.info(request, 'Use the Call or Send Email buttons on this worker profile to get in touch.')
    return redirect('employers:worker_detail', worker_id=worker.pk)


@worker_required
def followup_respond(request, pk):
    followup = get_object_or_404(FollowUp, pk=pk, connection__worker__user=request.user)
    # Ek follow-up ka sirf ek response hota hai (OneToOne). Agar pehle se
    # response hai to usi ko update karo, warna duplicate insert par error aata hai.
    existing = getattr(followup, 'response', None)
    form = FollowUpResponseForm(request.POST or None, instance=existing)
    if request.method == 'POST' and form.is_valid():
        response = form.save(commit=False)
        response.follow_up = followup
        response.save()
        followup.status = FollowUp.Status.RESPONDED
        followup.save()
        messages.success(request, 'Thank you. Your feedback has been recorded.')
        return redirect('workers:dashboard')
    return render(
        request, 'hiring/followup_respond.html', {'form': form, 'followup': followup}
    )
