from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import Area, Skill


class WorkerProfile(models.Model):
    class Availability(models.TextChoices):
        IMMEDIATE = 'immediate', 'Immediately'
        WITHIN_WEEK = 'week', 'Within a week'
        FLEXIBLE = 'flexible', 'Flexible'

    class Gender(models.TextChoices):
        WOMAN = 'woman', 'Woman'
        MAN = 'man', 'Man'
        OTHER = 'other', 'Other'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='worker_profile'
    )
    full_name = models.CharField(max_length=120)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    mobile = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    photo = models.FileField(upload_to='worker_photos/', null=True, blank=True)
    bio = models.TextField(blank=True)

    # Location (village / taluka / district / state / pincode)
    village = models.CharField(max_length=120, blank=True)
    taluka = models.CharField(max_length=120, blank=True)
    district = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True, default='Maharashtra')
    pincode = models.CharField(max_length=10, blank=True)

    area = models.ForeignKey(
        Area, on_delete=models.SET_NULL, null=True, blank=True, related_name='workers'
    )

    # Education
    education_level = models.CharField(max_length=60, blank=True)
    school = models.CharField(max_length=160, blank=True)
    qualification = models.CharField(max_length=160, blank=True)

    # Work preferences
    preferred_job = models.CharField(max_length=160, blank=True)
    experience = models.CharField(max_length=120, blank=True)
    expected_salary = models.PositiveIntegerField(
        null=True, blank=True, help_text='Expected monthly salary (INR)'
    )

    max_travel_km = models.PositiveSmallIntegerField(default=15)
    expected_min_wage = models.PositiveIntegerField(
        null=True, blank=True, help_text='Expected minimum daily wage (INR)'
    )
    availability = models.CharField(
        max_length=16, choices=Availability.choices, default=Availability.IMMEDIATE
    )
    onboarding_completed = models.BooleanField(default=False)
    profile_completed = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)

    # Discovery / notification preferences (Settings page)
    job_alerts = models.BooleanField(default=True)
    nearby_only = models.BooleanField(default=True)
    profile_visible = models.BooleanField(default=True)
    preferred_job_type = models.CharField(max_length=16, blank=True)
    minimum_salary = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['district', 'state'])]

    def __str__(self):
        return self.full_name or self.user.get_username()

    @property
    def location_display(self):
        parts = [self.village, self.taluka, self.district, self.state]
        return ', '.join(p for p in parts if p)

    @property
    def age(self):
        """Age is derived from date of birth and is never stored separately."""
        if not self.date_of_birth:
            return None
        today = timezone.localdate()
        birth = self.date_of_birth
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))

    @property
    def skills_text(self):
        return ', '.join(ws.skill.name for ws in self.skills.select_related('skill'))

    @property
    def profile_completion(self):
        """Percentage based on the 8 fields the reference app checks."""
        fields = (
            self.full_name, self.mobile, self.village, self.district,
            self.education_level, self.skills_text, self.experience, self.preferred_job,
        )
        filled = sum(1 for value in fields if str(value or '').strip())
        return round(filled / len(fields) * 100)

    def hired_by_employer_ids(self):
        """Un employers ke ids jinho ne is worker ko hire kiya hai.

        Hire hone ke baad worker ka naam baaki employers ko nahi dikhana hai,
        isliye ye ids privacy checks me use hoti hain.
        """
        return set(
            self.applications.filter(status='Hired').values_list('job__employer_id', flat=True)
        )


class Education(models.Model):
    class Level(models.TextChoices):
        SCHOOL = 'school', 'School (10th / 12th)'
        ITI = 'iti', 'ITI / Diploma'
        COLLEGE = 'college', 'College / Graduate'
        OTHER = 'other', 'Other'

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='education'
    )
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.SCHOOL)
    field = models.CharField(max_length=120, blank=True)
    institution = models.CharField(max_length=160, blank=True)
    year = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return f'{self.get_level_display()} - {self.field}'.strip(' -')


class WorkerSkill(models.Model):
    class Level(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        WORKING = 'working', 'Working'
        SKILLED = 'skilled', 'Skilled'

    class Source(models.TextChoices):
        SELF = 'self', 'Self declared'
        AI = 'ai', 'AI assessed'

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='skills'
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name='worker_skills'
    )
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.BEGINNER)
    confidence = models.FloatField(null=True, blank=True)
    years_experience = models.PositiveSmallIntegerField(default=0)
    verified = models.BooleanField(default=False)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.SELF)

    class Meta:
        unique_together = ('worker', 'skill')

    def __str__(self):
        return f'{self.worker} - {self.skill} ({self.get_level_display()})'


class SkillAssessment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        NEEDS_REVIEW = 'needs_review', 'Needs review'
        FAILED = 'failed', 'Failed'

    class Source(models.TextChoices):
        AI = 'ai', 'Gemini AI'
        RULE_BASED = 'rule_based', 'Rule-based fallback'

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='assessments'
    )
    # Legacy "main" skill. Kept for compatibility; the real per-skill data now
    # lives in the related DetectedSkill rows.
    skill = models.ForeignKey(
        Skill, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments'
    )
    video = models.FileField(upload_to='skill_videos/')
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    transcript = models.TextField(blank=True)
    ai_level = models.CharField(
        max_length=16, choices=WorkerSkill.Level.choices, blank=True
    )
    ai_confidence = models.FloatField(null=True, blank=True)
    ai_notes = models.TextField(blank=True)
    ai_report = models.JSONField(
        default=dict, blank=True,
        help_text='Full structured report from the Skill Assessment Agent.',
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    final_level = models.CharField(
        max_length=16, choices=WorkerSkill.Level.choices, blank=True
    )

    # --- Dynamic discovery metadata ---
    detected_profession = models.CharField(max_length=80, blank=True)
    profession_confidence = models.FloatField(null=True, blank=True)
    work_summary = models.TextField(blank=True)
    analysis_source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.RULE_BASED
    )
    ai_provider = models.CharField(max_length=40, blank=True)
    ai_model = models.CharField(max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Assessment #{self.pk} - {self.worker}'

    @property
    def is_ai(self):
        return self.analysis_source == self.Source.AI

    @property
    def accepted_skills(self):
        return self.detected_skills.filter(approval_status=DetectedSkill.Approval.ACCEPTED)


class DetectedSkill(models.Model):
    """One dynamically discovered skill from a single assessment video.

    The vision model discovers several skills per video and each is stored as
    its own row so it can be scored, evidenced, and approved/rejected by the
    worker independently of the others.
    """

    class Level(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        ADVANCED = 'advanced', 'Advanced'
        EXPERT = 'expert', 'Expert'

    class Evidence(models.TextChoices):
        OBSERVED = 'observed', 'Observed and assessable'
        PARTIAL = 'partial', 'Partially observed'
        CLAIMED = 'claimed', 'Claimed but not demonstrated'
        INSUFFICIENT = 'insufficient', 'Insufficient evidence'

    class Approval(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'

    # AI levels -> the 3 levels the public profile / matching engine uses.
    PROFILE_LEVEL = {
        'beginner': 'beginner',
        'intermediate': 'working',
        'advanced': 'skilled',
        'expert': 'skilled',
    }
    # Evidence states that carry a real, evidence-based score.
    ASSESSABLE = (Evidence.OBSERVED, Evidence.PARTIAL)

    assessment = models.ForeignKey(
        SkillAssessment, on_delete=models.CASCADE, related_name='detected_skills'
    )
    # Denormalised worker link: makes ownership/privacy checks and history
    # queries cheap without joining through the assessment every time.
    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='detected_skills'
    )
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True, help_text='0-100, null when not assessable')
    level = models.CharField(max_length=16, choices=Level.choices, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    reason = models.TextField(blank=True)
    strengths = models.JSONField(default=list, blank=True)
    improvements = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    evidence = models.JSONField(default=list, blank=True, help_text='Visual evidence / timestamps')
    limitations = models.TextField(blank=True)
    evidence_status = models.CharField(
        max_length=16, choices=Evidence.choices, default=Evidence.INSUFFICIENT
    )
    approval_status = models.CharField(
        max_length=16, choices=Approval.choices, default=Approval.PENDING
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.SET_NULL, null=True, blank=True, related_name='detected_skills'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-score', 'name']
        indexes = [models.Index(fields=['worker', 'approval_status'])]

    def __str__(self):
        return f'{self.name} ({self.get_level_display() or self.evidence_status})'

    @property
    def is_assessable(self):
        """True when the video gave enough evidence for a real score."""
        return self.evidence_status in self.ASSESSABLE and self.score is not None

    @property
    def profile_level(self):
        """Level mapped onto WorkerSkill.Level choices."""
        return self.PROFILE_LEVEL.get(self.level, 'beginner')

    @property
    def level_label(self):
        return self.get_level_display() or self.get_evidence_status_display()
