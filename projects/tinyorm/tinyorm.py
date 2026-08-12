"""TinyORM — a declarative model layer.

Read README.md in this directory for the full specification, then fill in
the pieces below. Grade your work with:

    uv run learn.py projects test tinyorm
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ORMError(Exception):
    """Base for everything this module raises."""


class ValidationError(ORMError, ValueError):
    """A value failed a field's validation rules."""


class DoesNotExist(ORMError):
    """No row matched."""


class MultipleObjectsReturned(ORMError):
    """More than one row matched a `get()`."""


class FieldError(ORMError):
    """An unknown field or lookup was referenced."""


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------
class Field:
    """Base descriptor. Learns its name via __set_name__."""

    def __init__(self, *, primary_key=False, null=False, default=None):
        ...

    def __set_name__(self, owner, name):
        ...

    def __get__(self, obj, objtype=None):
        ...

    def __set__(self, obj, value):
        ...

    def validate(self, value):
        """Raise ValidationError if `value` is unacceptable for this field."""
        ...


class IntegerField(Field):
    def __init__(self, *, min_value=None, max_value=None, **kwargs):
        ...


class StringField(Field):
    def __init__(self, *, max_length=None, choices=None, **kwargs):
        ...


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------
class QuerySet:
    """A lazy, immutable-by-convention query. Every operation returns a new one."""

    def __init__(self, model, filters=(), excludes=(), ordering=(),
                 limit_to=None, offset_by=0):
        ...

    def filter(self, **lookups):
        ...

    def exclude(self, **lookups):
        ...

    def order_by(self, *keys):
        ...

    def limit(self, n):
        ...

    def offset(self, n):
        ...

    def all(self):
        """Evaluate and return a list."""
        ...

    def get(self, **lookups):
        ...

    def count(self):
        ...

    def exists(self):
        ...

    def __iter__(self):
        ...

    def __len__(self):
        ...

    def __getitem__(self, key):
        ...


class Manager:
    """`Model.objects` — the entry point to a model's storage."""

    def __init__(self, model):
        ...


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class ModelMeta(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        ...


class Model(metaclass=ModelMeta):
    def __init__(self, **kwargs):
        ...

    def save(self):
        ...

    def delete(self):
        ...

    def to_dict(self):
        ...
