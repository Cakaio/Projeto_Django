"""Test settings using SQLite — avoids the need for a running PostgreSQL instance."""
from .settings import *  # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Monkey-patch: Django 4.2 / Python 3.14 incompatibility in BaseContext.__copy__
import django.template.context as _django_ctx

def _patched_base_context_copy(self):
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate

_django_ctx.BaseContext.__copy__ = _patched_base_context_copy
