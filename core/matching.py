"""Transparent demo matching score — React reference ke ``utils/matching.js`` ka port.

Weights (same as the reference app):
    skills 65% · location 20% · work type 10% · salary fit 5%
"""


def _norm(value):
    return str(value or '').strip().lower()


def _as_list(value):
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value or '').split(',')
    return [item.strip().lower() for item in items if str(item).strip()]


def _location_fits(worker_location, job_location):
    parts = [p for p in _norm(worker_location).replace('/', ' ').replace('-', ' ').split() if len(p) > 2]
    target = _norm(job_location)
    return any(part in target for part in parts)


def get_match_score(worker, job):
    """Return a 0–100 match score between a WorkerProfile and a Job."""
    worker_skills = _as_list(worker.skills_text)
    job_skills = _as_list(job.skills_list)
    worker_location = (worker.location_display or '').strip()
    job_location = (job.location_label or '').strip()
    worker_type = _norm(worker.preferred_job_type or worker.get_availability_display())
    job_type = _norm(job.get_job_type_display())
    desired_salary = worker.minimum_salary or worker.expected_salary or 0
    salary_max = job.wage_max or 0

    factors = []
    if job_skills:
        matched = sum(
            1
            for required in job_skills
            if any(skill == required or skill in required or required in skill for skill in worker_skills)
        )
        factors.append((matched / len(job_skills), 0.65))
    if worker_location and job_location:
        factors.append((1.0 if _location_fits(worker_location, job_location) else 0.0, 0.20))
    if worker_type and job_type:
        fits = worker_type == job_type or worker_type in job_type or job_type in worker_type
        factors.append((1.0 if fits else 0.0, 0.10))
    if desired_salary and salary_max:
        ratio = 1.0 if salary_max >= desired_salary else max(0.0, salary_max / desired_salary)
        factors.append((ratio, 0.05))

    if not factors:
        return 0

    active_weight = sum(weight for _value, weight in factors)
    score = sum(value * weight for value, weight in factors) / active_weight
    return round(score * 100)
