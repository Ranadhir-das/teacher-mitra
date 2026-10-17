from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.views.generic import TemplateView
from apps.accounts.models import User
from apps.accounts.permissions import can_manage_employees
from apps.leads.models import Lead
from apps.leads.permissions import visible_leads, optimized, can_create
from datetime import date, timedelta


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.role == User.Role.COUNSELLOR:
            from apps.accounts.counsellor_queries import counsellor_workload
        
            today = date.today()
        
            period = self.request.GET.get("period", "month")
        
            start_date = None
            end_date = today
        
            if period == "today":
                start_date = today
        
            elif period == "week":
                start_date = today - timedelta(days=today.weekday())
        
            elif period == "month":
                start_date = today.replace(day=1)
        
            elif period == "custom":
                start_raw = self.request.GET.get("start_date", "")
                end_raw = self.request.GET.get("end_date", "")
        
                try:
                    start_date = date.fromisoformat(start_raw)
                    end_date = date.fromisoformat(end_raw)
                except ValueError:
                    period = "month"
                    start_date = today.replace(day=1)
                    end_date = today
        
            if start_date and end_date and start_date > end_date:
                start_date, end_date = end_date, start_date
        
            context.update(
                counsellor_workload(
                    self.request.user,
                    self.request.user,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
        
            context["performance_period"] = period
            context["performance_start_date"] = start_date
            context["performance_end_date"] = end_date
        
            context["today_followups"] = (
                context["today_followups"]
                .select_related("lead")[:10]
            )
        
            context["pending_applications"] = (
                context["pending_applications"]
                .select_related("lead", "course")[:10]
            )
        queryset = visible_leads(self.request.user).filter(is_active=True)
        counts = dict(queryset.order_by().values_list("status").annotate(total=Count("id")))
        cards = [{"label": "Total leads", "value": sum(counts.values()), "note": "Active leads visible to you"}]
        for label, status in (("New leads", Lead.Status.NEW), ("Assigned leads", Lead.Status.ASSIGNED),
                              ("Interested leads", Lead.Status.INTERESTED), ("Counselling leads", Lead.Status.COUNSELLING), ("Lost leads", Lead.Status.LOST)):
            cards.append({"label": label, "value": counts.get(status, 0), "note": "Current lead status"})
        if can_manage_employees(self.request.user):
            cards.append({"label": "Active employees", "value": User.objects.filter(is_active=True).exclude(role=User.Role.PARTNER).count(), "note": "Live internal account count"})
            from apps.partners.models import Partner
            cards.extend([
                {"label": "Total partners", "value": Partner.objects.count(), "note": "Registered partners"},
                {"label": "Active partners", "value": Partner.objects.filter(status=Partner.Status.ACTIVE).count(), "note": "Approved partners"},
                {"label": "Partner leads", "value": queryset.filter(partner__isnull=False).count(), "note": "Active attributed leads"},
            ])
        total = sum(counts.values())
        context.update(cards=cards, recent_leads=optimized(queryset)[:5], can_create_lead=can_create(self.request.user),
            distribution=[{"label": label, "count": counts.get(value, 0), "percent": round(counts.get(value, 0) * 100 / total) if total else 0}
                          for value, label in Lead.Status.choices if counts.get(value, 0)],
            sources=[{"label": dict(Lead.Source.choices).get(row["lead_source"], row["lead_source"]), "count": row["total"]}
                     for row in queryset.order_by().values("lead_source").annotate(total=Count("id")).order_by("-total", "lead_source")[:5]])
        return context
