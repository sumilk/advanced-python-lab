# TinyORM — a declarative model layer

Build the part of an ORM that everyone recognises but few have written: the
declarative model class, backed by descriptors and a metaclass, with a
chainable query builder over an in-memory store.

**Lessons drawn on:** 02 (data model), 09 (descriptors), 10 (class creation),
13 (typing).

## What you are building

```python
class User(Model):
    id = IntegerField(primary_key=True)
    name = StringField(max_length=50)
    age = IntegerField(min_value=0, null=True)
    email = StringField(default="")

u = User(id=1, name="ada", age=36)
u.save()

User.objects.filter(age__gte=30).order_by("-name").limit(5).all()
```

## Requirements

### 1. Fields are descriptors

`Field` is the base; `IntegerField` and `StringField` specialise it.

- learn their own attribute name via `__set_name__`
- store values **per instance**, never on the descriptor
- `null=False` (the default) rejects `None` with `ValidationError`
- `default=` supplies a value when the field is omitted
- reading a field that was never set and has no default returns `None`
- `IntegerField(min_value=, max_value=)` — inclusive bounds, `ValidationError`
  outside them; rejects `bool` and non-integers with `ValidationError`
- `StringField(max_length=, choices=)` — `ValidationError` on a non-`str`,
  on over-length, or on a value outside `choices`
- every `ValidationError` message contains the field's name
- accessing a field on the **class** returns the descriptor itself

### 2. `Model` is built by `ModelMeta`

- `Model._fields` → `dict[name, Field]` in declaration order, **including**
  fields inherited from a parent model (parent fields first)
- `Model._meta` → `{"table": <lowercased class name>, "pk": <primary key name>}`
- exactly one field may set `primary_key=True`; zero or two raises
  `TypeError` at class creation
- the abstract base `Model` itself has no primary key and must not raise
- `Model(**kwargs)` assigns every field, applying defaults and validating;
  an unknown keyword raises `TypeError`
- `repr(u)` → `User(id=1, name='ada', age=36, email='')` in field order
- `u == v` compares type and all field values; `hash(u)` is derived from
  the type and primary key, and raises `TypeError` when the primary key has
  no value
- `u.to_dict()` → a plain dict in field order

### 3. A per-model manager and query builder

- `User.objects` is a manager bound to `User`; two model classes never share
  storage
- `u.save()` inserts or updates by primary key and returns `self`
- `u.delete()` removes it; deleting an absent row raises `DoesNotExist`
- `User.objects.all()` → list of models in insertion order
- `User.objects.get(**lookups)` → exactly one, else `DoesNotExist` or
  `MultipleObjectsReturned`
- `User.objects.count()`, `.exists()`
- `filter(**lookups)` / `exclude(**lookups)` return a **new** `QuerySet`
  (never mutate the receiver — chaining must be safe to fork)
- lookups: `field=value` (exact), `field__gte`, `__gt`, `__lte`, `__lt`,
  `__ne`, `__in`, `__contains` (substring), `__startswith`, `__isnull`
- an unknown lookup or unknown field raises `FieldError`
- `order_by("age", "-name")` — leading `-` means descending; a `None` value
  sorts before any other value
- `limit(n)`, `offset(n)`
- a `QuerySet` is **lazy**: nothing is evaluated until you call `.all()`,
  iterate it, take `len()`, or index it
- `QuerySet` supports `len()`, iteration, indexing, and slicing (a slice
  returns a new lazy `QuerySet`)

### 4. Exceptions

`ORMError` is the base. `ValidationError`, `DoesNotExist`,
`MultipleObjectsReturned` and `FieldError` all inherit from it, and
`ValidationError` is also a `ValueError`.

## Grading

```bash
uv run learn.py projects test tinyorm
```

## Hints

- Collect the fields in `ModelMeta.__new__` by scanning the namespace for
  `Field` instances *before* calling `super().__new__`; merge in the parents'
  `_fields` first so inherited fields come first.
- Give each model class its own storage — a `dict` created in the metaclass —
  or every model will share one table.
- Build lookups as `(field_name, operator)` pairs parsed once, then compile
  each to a small predicate function.
- For `order_by`, sort once per key in reverse order and rely on sort
  stability rather than building a compound key — it handles mixed
  directions for free.
- `None` sorting first falls out of a key like `(value is not None, value)`.
