"""manage.py add_default_documents: put the Center's standard documents on My tasks (skips any already there)."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.reporting.models import File, HelpfulDocument

DIR = Path(settings.BASE_DIR) / "fixtures" / "documents"
DEFAULTS = [
    (
        "How to sign with an Adobe digital signature",
        "Step-by-step, for the MFTRP certification",
        "Adobe_Digital_Signature_Guide.pdf",
        "",
    ),
    ("CNAP website", "News, people, cores and events", "", "https://www.k-state.edu/cnap/"),
]


class Command(BaseCommand):
    help = "Add the Adobe signing guide and the CNAP website to Helpful documents."

    def handle(self, *args, **kw):
        # The Phase 2 PL Guidelines were retired as outdated (MW 2026-10-28)
        n = HelpfulDocument.objects.filter(title="CNAP Phase 2 PL Guidelines", is_active=True).update(is_active=False)
        if n:
            self.stdout.write("CNAP Phase 2 PL Guidelines: removed (outdated)")
        owner = (
            User.objects.filter(is_superuser=True).first() or User.objects.order_by("pk").first()
        )
        for i, (title, note, fname, url) in enumerate(DEFAULTS):
            if HelpfulDocument.objects.filter(title=title, is_active=True).exists():
                self.stdout.write(f"{title}: already there")
                continue
            f = None
            if fname:
                data = (DIR / fname).read_bytes()
                f = File(
                    original_filename=fname,
                    content_type="application/pdf",
                    byte_size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    uploaded_by=owner,
                )
                f.storage_key.save(fname, ContentFile(data), save=False)
                f.save()
            HelpfulDocument.objects.create(title=title, note=note, file=f, url=url, sort_order=i)
            self.stdout.write(f"{title}: added")
