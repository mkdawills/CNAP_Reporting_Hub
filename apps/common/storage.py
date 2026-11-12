"""Static file storage for development (MW 2026-11-12).

Browsers kept old copies of the stylesheets and scripts, so a fix pulled into a Codespace did not show until a hard
refresh. Each URL now carries the file's last-changed time, so a changed file is fetched fresh. Production already
uses hashed file names (CompressedManifestStaticFilesStorage) and does not use this class.
"""

import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        path = finders.find(name) if name else None
        if isinstance(path, str):
            try:
                return f"{url}?v={int(os.path.getmtime(path))}"
            except OSError:
                pass
        return url
