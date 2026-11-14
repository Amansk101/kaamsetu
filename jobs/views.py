from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from agents.logic import match_score, parse_job_listing, verify_listing
from core.decorators import employer_required
from core.models import Area, Skill
from employers.models import EmployerProfile
from hiring.models import JobInterest
from workers.models import WorkerProfile

from .forms import JobPostForm
from .models import Job, JobVerification

_STATUS_MAP = {
    'passed': Job.Status.ACTIVE,
    'flagged': Job.Status.PENDING,
    'blocked': Job.Status.REJECTED,
}


@employer_required
def post_job(request):
    profile = EmployerProfile.objects.get_or_create(
        user=request.user, defaults={'business_name': request.user.username}
    )[0]
    form = JobPostForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        raw = form.cleaned_data['raw_description']
        structured = parse_job_listing(raw)
        verify = verify_listing(raw, structured)

        skill = Skill.objects.filter(name=structured['skill_name']).first() if structured['skill_name'] else None
        area = Area.objects.filter(name=structured['area_name']).first() if structured['area_name'] else profile.area

        job = Job.objects.create(
            employer=profile,
            title=structured['title'],
            raw_description=raw,
            skill=skill,
            workers_needed=structured['workers_needed'],
            wage_min=structured['wage_min'],
            wage_max=structured['wage_max'],
            wage_period=structured['wage_period'],
            job_type=structured['job_type'],
            area=area,
            status=_STATUS_MAP.get(verify['status'], Job.Status.PENDING),
        )
        JobVerification.objects.create(
            job=job,
            status=verify['status'],
            risk_score=verify['risk_score'],
            flags=verify['flags'],
            summary=verify['summary'],
            structured_data=structured,
        )

        if verify['status'] == 'passed':
            messages.success(request, 'Job passed the automated safety check and is now live.')
        elif verify['status'] == 'flagged':
            messages.warning(request, 'Job flagged — it will go live after manual review.')
        else:
            messages.error(request, 'Job blocked: asking workers for money is not allowed.')
        return redirect('jobs:detail', pk=job.pk)

    return render(request, 'jobs/post_job.html', {'form': form})


def job_detail(request, pk):
    job = get_object_or_404(
        Job.objects.select_related('skill', 'area', 'employer', 'verification'), pk=pk
    )
    score = reasons = interest = None
    if request.user.is_authenticated and request.user.is_worker:
        profile = WorkerProfile.objects.filter(user=request.user).first()
        if profile:
            score, reasons = match_score(profile, job)
            interest = JobInterest.objects.filter(job=job, worker=profile).first()
    return render(
        request,
        'jobs/detail.html',
        {'job': job, 'score': score, 'reasons': reasons, 'interest': interest},
    )
