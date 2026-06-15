from django.db import migrations


def normalize_existing_phones(apps, schema_editor):
    User = apps.get_model("core", "User")

    users = list(User.objects.all().only("id", "phone"))
    normalized_map = {}

    for user in users:
        digits = "".join(ch for ch in (user.phone or "") if ch.isdigit())
        if not digits or len(digits) > 15:
            raise RuntimeError(f"User {user.id} has invalid phone and cannot be normalized: {user.phone!r}")
        normalized = f"+{digits}"

        if normalized in normalized_map and normalized_map[normalized] != user.id:
            other_id = normalized_map[normalized]
            raise RuntimeError(
                "Phone normalization collision detected between "
                f"user {other_id} and user {user.id} -> {normalized}"
            )
        normalized_map[normalized] = user.id

    for user in users:
        digits = "".join(ch for ch in (user.phone or "") if ch.isdigit())
        normalized = f"+{digits}"
        if user.phone != normalized:
            User.objects.filter(id=user.id).update(phone=normalized)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(normalize_existing_phones, migrations.RunPython.noop),
    ]
