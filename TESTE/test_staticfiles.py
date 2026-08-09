from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class StaticFilesSettingsTests(SimpleTestCase):
    def test_source_and_collection_directories_are_separate(self):
        self.assertIn(settings.BASE_DIR / 'static', settings.STATICFILES_DIRS)
        self.assertEqual(settings.STATIC_ROOT, settings.BASE_DIR / 'staticfiles')
        self.assertNotIn(Path(settings.STATIC_ROOT), settings.STATICFILES_DIRS)

    def test_main_stylesheet_is_discoverable(self):
        stylesheet = finders.find('css/pcf.css')

        self.assertIsNotNone(stylesheet)
        self.assertEqual(Path(stylesheet), settings.BASE_DIR / 'static/css/pcf.css')
