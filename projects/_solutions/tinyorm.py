"""TinyORM — reference solution.

Deliberately written the way you would actually ship it: small classes, one
responsibility each, and the awkward parts (lookup parsing, ordering,
per-model storage) isolated so they can be read in one sitting.
"""
from __future__ import annotations

import operator
from typing import Any


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


UNSET = object()


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------
class Field:
    def __init__(self, *, primary_key: bool = False, null: bool = False,
                 default: Any = UNSET):
        self.primary_key = primary_key
        self.null = null
        self.default = default
        self.name: str | None = None

    def __set_name__(self, owner, name):
        self.name = name
        self.private = f"_value_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.private)

    def __set__(self, obj, value):
        self.validate(value)
        obj.__dict__[self.private] = value

    # -- validation --------------------------------------------------------
    def validate(self, value):
        if value is None:
            if not self.null:
                raise ValidationError(f"{self.name}: null is not allowed")
            return
        self.validate_value(value)

    def validate_value(self, value):
        """Type-specific checks. Only ever called with a non-None value."""

    def resolve_default(self):
        return None if self.default is UNSET else self.default

    def __repr__(self):
        return f"{type(self).__name__}(name={self.name!r})"


class IntegerField(Field):
    def __init__(self, *, min_value=None, max_value=None, **kwargs):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value

    def validate_value(self, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(
                f"{self.name}: expected an int, got {type(value).__name__}"
            )
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(f"{self.name}: {value} is below {self.min_value}")
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(f"{self.name}: {value} is above {self.max_value}")


class StringField(Field):
    def __init__(self, *, max_length=None, choices=None, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length
        self.choices = tuple(choices) if choices is not None else None

    def validate_value(self, value):
        if not isinstance(value, str):
            raise ValidationError(
                f"{self.name}: expected a str, got {type(value).__name__}"
            )
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(
                f"{self.name}: {len(value)} characters exceeds max_length "
                f"{self.max_length}"
            )
        if self.choices is not None and value not in self.choices:
            raise ValidationError(
                f"{self.name}: {value!r} is not one of {list(self.choices)}"
            )


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def _isnull(value, expected):
    return (value is None) is bool(expected)


def _compare(op):
    """Wrap an operator so a None operand never explodes; None sorts lowest."""
    def apply(value, target):
        if value is None or target is None:
            return False
        return op(value, target)
    return apply


LOOKUPS = {
    "exact": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "gt": _compare(operator.gt),
    "gte": _compare(operator.ge),
    "lt": _compare(operator.lt),
    "lte": _compare(operator.le),
    "in": lambda v, t: v in t,
    "contains": lambda v, t: v is not None and t in v,
    "startswith": lambda v, t: isinstance(v, str) and v.startswith(t),
    "isnull": _isnull,
}


def parse_lookup(model, key: str, target: Any):
    """'age__gte' -> a predicate taking a model instance."""
    field_name, _, suffix = key.partition("__")
    operation = suffix or "exact"

    if field_name not in model._fields:
        raise FieldError(
            f"{model.__name__} has no field {field_name!r}; "
            f"known fields: {sorted(model._fields)}"
        )
    if operation not in LOOKUPS:
        raise FieldError(
            f"unknown lookup {operation!r}; known lookups: {sorted(LOOKUPS)}"
        )

    test = LOOKUPS[operation]
    return lambda row: test(getattr(row, field_name), target)


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------
class QuerySet:
    def __init__(self, model, filters=(), excludes=(), ordering=(),
                 limit_to=None, offset_by=0):
        self.model = model
        self._filters = tuple(filters)
        self._excludes = tuple(excludes)
        self._ordering = tuple(ordering)
        self._limit = limit_to
        self._offset = offset_by

    # -- chaining: every method forks -------------------------------------
    def _fork(self, **changes):
        base = {
            "filters": self._filters,
            "excludes": self._excludes,
            "ordering": self._ordering,
            "limit_to": self._limit,
            "offset_by": self._offset,
        }
        base.update(changes)
        return QuerySet(self.model, **base)

    def filter(self, **lookups):
        predicates = tuple(parse_lookup(self.model, k, v) for k, v in lookups.items())
        return self._fork(filters=self._filters + predicates)

    def exclude(self, **lookups):
        predicates = tuple(parse_lookup(self.model, k, v) for k, v in lookups.items())
        return self._fork(excludes=self._excludes + predicates)

    def order_by(self, *keys):
        for key in keys:
            name = key[1:] if key.startswith("-") else key
            if name not in self.model._fields:
                raise FieldError(f"{self.model.__name__} has no field {name!r}")
        return self._fork(ordering=self._ordering + tuple(keys))

    def limit(self, n):
        return self._fork(limit_to=n)

    def offset(self, n):
        return self._fork(offset_by=n)

    # -- evaluation --------------------------------------------------------
    def _evaluate(self):
        rows = list(self.model._storage.values())
        rows = [r for r in rows if all(p(r) for p in self._filters)]
        rows = [r for r in rows if not any(p(r) for p in self._excludes)]

        # Sort stability lets us apply keys right-to-left for mixed directions.
        for key in reversed(self._ordering):
            descending = key.startswith("-")
            name = key[1:] if descending else key
            rows.sort(
                key=lambda row, n=name: (
                    getattr(row, n) is not None, getattr(row, n)
                ),
                reverse=descending,
            )

        if self._offset:
            rows = rows[self._offset:]
        if self._limit is not None:
            rows = rows[:self._limit]
        return rows

    def all(self):
        return self._evaluate()

    def get(self, **lookups):
        found = (self.filter(**lookups) if lookups else self)._evaluate()
        if not found:
            raise DoesNotExist(f"no {self.model.__name__} matching {lookups}")
        if len(found) > 1:
            raise MultipleObjectsReturned(
                f"{len(found)} {self.model.__name__} rows matched {lookups}"
            )
        return found[0]

    def count(self):
        return len(self._evaluate())

    def exists(self):
        return bool(self._evaluate())

    def __iter__(self):
        return iter(self._evaluate())

    def __len__(self):
        return len(self._evaluate())

    def __getitem__(self, key):
        if isinstance(key, slice):
            start = key.start or 0
            stop = key.stop
            return self._fork(
                offset_by=self._offset + start,
                limit_to=None if stop is None else stop - start,
            )
        return self._evaluate()[key]

    def __repr__(self):
        return f"<QuerySet {self.model.__name__} filters={len(self._filters)}>"


class Manager:
    def __init__(self, model):
        self.model = model

    def get_queryset(self):
        return QuerySet(self.model)

    def all(self):
        return self.get_queryset().all()

    def filter(self, **lookups):
        return self.get_queryset().filter(**lookups)

    def exclude(self, **lookups):
        return self.get_queryset().exclude(**lookups)

    def order_by(self, *keys):
        return self.get_queryset().order_by(*keys)

    def get(self, **lookups):
        return self.get_queryset().get(**lookups)

    def count(self):
        return self.get_queryset().count()

    def exists(self):
        return self.get_queryset().exists()

    def create(self, **kwargs):
        return self.model(**kwargs).save()

    def __iter__(self):
        return iter(self.get_queryset())


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class ModelMeta(type):
    def __new__(mcls, name, bases, namespace, **kwargs):
        fields: dict[str, Field] = {}
        for base in bases:                       # inherited fields come first
            fields.update(getattr(base, "_fields", {}))
        fields.update({k: v for k, v in namespace.items() if isinstance(v, Field)})

        primary_keys = [n for n, f in fields.items() if f.primary_key]
        if len(primary_keys) > 1:
            raise TypeError(
                f"{name} declares {len(primary_keys)} primary keys: {primary_keys}"
            )
        if fields and not primary_keys:
            raise TypeError(f"{name} declares fields but no primary_key")

        cls = super().__new__(mcls, name, bases, namespace)
        cls._fields = fields
        cls._meta = {
            "table": name.lower(),
            "pk": primary_keys[0] if primary_keys else None,
        }
        cls._storage = {}                        # one table per model class
        cls.objects = Manager(cls)
        return cls


class Model(metaclass=ModelMeta):
    def __init__(self, **kwargs):
        unknown = set(kwargs) - set(self._fields)
        if unknown:
            raise TypeError(
                f"{type(self).__name__} got unexpected field(s): {sorted(unknown)}"
            )
        for name, field in self._fields.items():
            setattr(self, name, kwargs.get(name, field.resolve_default()))

    # -- persistence -------------------------------------------------------
    @property
    def pk(self):
        key = self._meta["pk"]
        return getattr(self, key) if key else None

    def save(self):
        if self.pk is None:
            raise ValidationError(
                f"{type(self).__name__}: cannot save without a primary key"
            )
        self._storage[self.pk] = self
        return self

    def delete(self):
        if self.pk not in self._storage:
            raise DoesNotExist(
                f"{type(self).__name__} with pk={self.pk!r} is not stored"
            )
        del self._storage[self.pk]
        return self

    # -- protocol ----------------------------------------------------------
    def to_dict(self):
        return {name: getattr(self, name) for name in self._fields}

    def __repr__(self):
        inner = ", ".join(f"{k}={v!r}" for k, v in self.to_dict().items())
        return f"{type(self).__name__}({inner})"

    def __eq__(self, other):
        if type(other) is not type(self):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __hash__(self):
        if self.pk is None:
            raise TypeError(
                f"unhashable: {type(self).__name__} has no primary key value"
            )
        return hash((type(self), self.pk))
