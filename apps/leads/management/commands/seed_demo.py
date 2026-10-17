from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.accounts.models import User, Team
from apps.leads.models import Lead, Tag
from apps.leads import services


class Command(BaseCommand):
    help = "Create 20 synthetic demo leads, demo teams and unusable-password demo accounts. Safe to rerun."

    @transaction.atomic
    def handle(self, *args, **options):
        def account(key, name, role):
            email = f"alp-demo-{key}@example.invalid"
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email, name=name, role=role)
            if user.role != role or not user.is_active:
                raise ValueError(f"Demo account {email} was modified; seed aborted without overwriting it.")
            return user

        actor = account("admin", "Demo Administrator", User.Role.ADMIN)
        leaders = [account(f"leader-{i}", f"Demo Team Leader {i}", User.Role.TEAM_LEADER) for i in (1, 2)]
        counsellors = [account(f"counsellor-{i}", f"Demo Counsellor {i}", User.Role.COUNSELLOR) for i in range(1, 5)]
        teams = []
        for i, leader in enumerate(leaders):
            team, created = Team.objects.get_or_create(name=f"Demo Admissions Team {i + 1}", defaults={"leader": leader})
            if created:
                team.members.set(counsellors[i * 2:i * 2 + 2])
            teams.append(team)
        tags = [Tag.objects.get_or_create(name=name)[0] for name in ("HOT", "MBA", "MCA", "URGENT", "CALLBACK", "HIGH_BUDGET", "ONLINE", "FOLLOW_UP")]
        statuses = list(Lead.Status.values)
        courses = ["Online MBA", "MCA", "BBA", "B.Com", "M.Sc Data Science"]
        places = [("Pune", "Maharashtra"), ("Jaipur", "Rajasthan"), ("Bengaluru", "Karnataka"), ("Lucknow", "Uttar Pradesh")]
        created_count = 0
        for i in range(20):
            email = f"alp-demo-student-{i + 1:02d}@example.invalid"
            if Lead.objects.filter(email=email).exists():
                continue
            city, state = places[i % len(places)]
            target = statuses[i % len(statuses)]
            counsellor = None if target == Lead.Status.NEW else counsellors[i % 4]
            team = teams[(i % 4) // 2] if counsellor else None
            lead = services.create_lead(actor, {
                "full_name": f"Demo Student {i + 1:02d}", "phone": f"120255501{i + 60:02d}", "email": email,
                "city": city, "state": state, "highest_qualification": "Bachelor's degree", "institution_name": "Example Demo College",
                "passing_year": 2024, "percentage_or_cgpa": "8.2/10", "desired_course": courses[i % 5],
                "preferred_university": "Example Demo University", "preferred_study_mode": Lead.StudyMode.ONLINE,
                "budget": Decimal(80000 + i * 5000), "career_goal": "Develop practical skills for career growth.",
                "priority": Lead.Priority.values[i % 4], "lead_source": Lead.Source.values[i % 10],
                "general_notes": "Synthetic demonstration record; not a real student.",
            }, counsellor=counsellor, team=team, tags=[tags[i % 8], tags[6]])
            if target not in (Lead.Status.NEW, Lead.Status.ASSIGNED):
                services.change_status(actor, lead.pk, Lead.Status.CONTACTED, "Demo introductory discussion.")
                if target != Lead.Status.CONTACTED:
                    services.change_status(actor, lead.pk, target, "Demo lifecycle example.")
            services.add_note(actor, lead.pk, "Demo student requested details about course duration and flexible learning options.")
            if i == 3:
                services.assign_lead(actor, lead.pk, counsellors[2], teams[1], "Demo workload balancing.")
            created_count += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created_count} synthetic leads. New demo accounts have no usable passwords; no existing records were reset."))
