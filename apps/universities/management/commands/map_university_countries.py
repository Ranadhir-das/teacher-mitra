from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.universities.models import Country, University


class Command(BaseCommand):
    help = "List unmapped universities or explicitly map one to an existing country (after migration 0003)."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true")
        parser.add_argument("--university", type=int)
        parser.add_argument("--country", type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        if options["list"]:
            for pk, name in University.objects.filter(country__isnull=True).values_list("pk", "name"):
                self.stdout.write(f"{pk}: {name}")
            return
        if not options["university"] or not options["country"]:
            raise CommandError("Supply --list or both --university ID and --country ID.")
        university = University.objects.select_for_update().filter(pk=options["university"], country__isnull=True).first()
        country = Country.objects.filter(pk=options["country"], is_active=True).first()
        if not university or not country:
            raise CommandError("Choose an unmapped university and an existing active country.")
        university.country = country
        university.full_clean()
        university.save(update_fields=["country", "updated_at"])
        self.stdout.write(f"Mapped university {university.pk} to country {country.pk}.")
