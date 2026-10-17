from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CountryMappingMigrationTests(TransactionTestCase):
    def test_legacy_location_is_preserved_and_unmapped_rows_block_finalization(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate([("universities", "0002_country")])
        state = executor.loader.project_state([("universities", "0002_country")]).apps
        university = state.get_model("universities", "University").objects.create(
            name="Legacy University", city="Legacy city", state="Legacy state", description="Original description")
        try:
            executor = MigrationExecutor(connection)
            target = [("universities", "0003_remove_university_university_name_ci_unique_and_more")]
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            university_model = apps.get_model("universities", "University")
            saved = university_model.objects.get(pk=university.pk)
            self.assertIsNone(saved.country_id)
            self.assertIn("Original description", saved.description)
            self.assertIn("Legacy city, Legacy state", saved.description)
            self.assertFalse(apps.get_model("universities", "Country").objects.exists())
            with self.assertRaisesRegex(RuntimeError, "Country mapping required"):
                MigrationExecutor(connection).migrate([("universities", "0004_require_university_country")])
            country = apps.get_model("universities", "Country").objects.create(name="Explicitly mapped country")
            from django.core.management import call_command
            from io import StringIO
            output = StringIO()
            call_command("map_university_countries", university=university.pk, country=country.pk, stdout=output)
            self.assertIn("Mapped university", output.getvalue())
            MigrationExecutor(connection).migrate(latest)
            from .models import University
            self.assertEqual(University.objects.get(pk=university.pk).country_id, country.pk)
        finally:
            # Restore schema even when an assertion fails, without inventing a country.
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM universities_university WHERE id = %s", [university.pk])
            MigrationExecutor(connection).migrate(latest)
