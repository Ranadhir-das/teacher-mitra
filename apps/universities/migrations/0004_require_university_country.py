import django.db.models.deletion
from django.db import migrations, models


def require_mappings(apps, schema_editor):
    University = apps.get_model("universities", "University")
    missing = list(University.objects.using(schema_editor.connection.alias).filter(country__isnull=True).values_list("pk", "name"))
    if missing:
        raise RuntimeError("Country mapping required; no countries were guessed. Run manage.py map_university_countries --list, then --university ID --country ID for each entry, and retry migrate. Universities: " + repr(missing))


class Migration(migrations.Migration):
    dependencies = [("universities", "0003_remove_university_university_name_ci_unique_and_more")]
    operations = [
        migrations.RunPython(require_mappings, migrations.RunPython.noop),
        migrations.AlterField(model_name="university", name="country", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="universities", to="universities.country")),
    ]
