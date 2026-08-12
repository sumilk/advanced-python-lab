"""Grading suite for the TinyORM capstone.

    uv run learn.py projects test tinyorm
"""
from __future__ import annotations

import pytest

from conftest import load

pytestmark = pytest.mark.project

orm = load("tinyorm")


@pytest.fixture
def models():
    """A fresh pair of model classes per test, so storage never leaks."""
    class User(orm.Model):
        id = orm.IntegerField(primary_key=True)
        name = orm.StringField(max_length=50)
        age = orm.IntegerField(min_value=0, null=True)
        email = orm.StringField(default="")

    class Post(orm.Model):
        id = orm.IntegerField(primary_key=True)
        title = orm.StringField(max_length=100)
        status = orm.StringField(choices=("draft", "live"), default="draft")

    return User, Post


@pytest.fixture
def users(models):
    User, _ = models
    rows = [
        User(id=1, name="ada", age=36, email="ada@x.com"),
        User(id=2, name="bob", age=29),
        User(id=3, name="cy", age=41, email="cy@x.com"),
        User(id=4, name="dee", age=None),
        User(id=5, name="eve", age=29, email="eve@x.com"),
    ]
    for row in rows:
        row.save()
    return User, rows


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------
class TestFields:
    def test_values_are_per_instance(self, models):
        User, _ = models
        a, b = User(id=1, name="a"), User(id=2, name="b")
        assert (a.name, b.name) == ("a", "b")
        assert (a.id, b.id) == (1, 2)

    def test_class_access_returns_the_descriptor(self, models):
        User, _ = models
        assert isinstance(User.name, orm.StringField)
        assert isinstance(User.age, orm.IntegerField)

    def test_default_and_unset(self, models):
        User, _ = models
        u = User(id=1, name="a")
        assert u.email == "", "a field with a default should use it"
        assert u.age is None, "a nullable field with no default reads as None"

    def test_null_rejected_unless_allowed(self, models):
        User, _ = models
        with pytest.raises(orm.ValidationError) as info:
            User(id=1, name=None)
        assert "name" in str(info.value)
        User(id=1, name="a", age=None)          # age is null=True

    def test_integer_validation(self, models):
        User, _ = models
        u = User(id=1, name="a")
        for bad in ("30", 3.5, True):
            with pytest.raises(orm.ValidationError):
                u.age = bad
        with pytest.raises(orm.ValidationError) as info:
            u.age = -1
        assert "age" in str(info.value)
        u.age = 0                                # min_value is inclusive

    def test_string_validation(self, models):
        User, Post = models
        u = User(id=1, name="a")
        with pytest.raises(orm.ValidationError):
            u.name = 123
        with pytest.raises(orm.ValidationError) as info:
            u.name = "x" * 51
        assert "name" in str(info.value)
        u.name = "x" * 50                        # max_length is inclusive

        p = Post(id=1, title="t")
        with pytest.raises(orm.ValidationError):
            p.status = "archived"
        p.status = "live"

    def test_validation_error_is_a_value_error(self):
        assert issubclass(orm.ValidationError, ValueError)
        assert issubclass(orm.ValidationError, orm.ORMError)


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------
class TestModel:
    def test_fields_in_declaration_order(self, models):
        User, _ = models
        assert list(User._fields) == ["id", "name", "age", "email"]

    def test_meta(self, models):
        User, Post = models
        assert User._meta["table"] == "user"
        assert User._meta["pk"] == "id"
        assert Post._meta["table"] == "post"

    def test_inherited_fields_come_first(self):
        class Base(orm.Model):
            id = orm.IntegerField(primary_key=True)
            created = orm.StringField(default="today")

        class Child(Base):
            extra = orm.StringField(default="x")

        assert list(Child._fields) == ["id", "created", "extra"]
        c = Child(id=1)
        assert (c.created, c.extra) == ("today", "x")

    def test_missing_primary_key_is_rejected(self):
        with pytest.raises(TypeError):
            class NoPk(orm.Model):
                name = orm.StringField()

    def test_two_primary_keys_are_rejected(self):
        with pytest.raises(TypeError):
            class TwoPk(orm.Model):
                a = orm.IntegerField(primary_key=True)
                b = orm.IntegerField(primary_key=True)

    def test_abstract_base_is_fine(self):
        assert orm.Model._fields == {}
        assert orm.Model._meta["pk"] is None

    def test_unknown_kwarg(self, models):
        User, _ = models
        with pytest.raises(TypeError):
            User(id=1, name="a", nope=1)

    def test_repr_and_to_dict(self, models):
        User, _ = models
        u = User(id=1, name="ada", age=36)
        assert repr(u) == "User(id=1, name='ada', age=36, email='')", repr(u)
        assert u.to_dict() == {"id": 1, "name": "ada", "age": 36, "email": ""}

    def test_equality_and_hashing(self, models):
        User, Post = models
        assert User(id=1, name="a") == User(id=1, name="a")
        assert User(id=1, name="a") != User(id=2, name="a")
        assert User(id=1, name="a") != Post(id=1, title="a")
        assert len({User(id=1, name="a"), User(id=1, name="a")}) == 1, (
            "equal models must collapse in a set"
        )
        # Hashing by pk is legal even though these two are unequal: equal
        # objects hash equal, which is the whole contract. Collisions are fine.
        assert hash(User(id=1, name="a")) == hash(User(id=1, name="b"))

    def test_no_primary_key_value_is_unhashable(self):
        class Draft(orm.Model):
            id = orm.IntegerField(primary_key=True, null=True)
            title = orm.StringField(default="")

        assert hash(Draft(id=1)) == hash(Draft(id=1))
        with pytest.raises(TypeError):
            hash(Draft())


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
class TestStorage:
    def test_models_do_not_share_storage(self, models):
        User, Post = models
        User(id=1, name="a").save()
        assert User.objects.count() == 1
        assert Post.objects.count() == 0, "each model class needs its own table"

    def test_save_returns_self_and_updates(self, models):
        User, _ = models
        u = User(id=1, name="a")
        assert u.save() is u
        assert User.objects.count() == 1
        u.name = "renamed"
        u.save()
        assert User.objects.count() == 1, "saving the same pk should update, not insert"
        assert User.objects.get(id=1).name == "renamed"

    def test_delete(self, models):
        User, _ = models
        u = User(id=1, name="a").save()
        u.delete()
        assert User.objects.count() == 0
        with pytest.raises(orm.DoesNotExist):
            u.delete()

    def test_all_preserves_insertion_order(self, users):
        User, rows = users
        assert [u.name for u in User.objects.all()] == ["ada", "bob", "cy", "dee", "eve"]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
class TestQueries:
    def test_exact_and_get(self, users):
        User, _ = users
        assert User.objects.get(name="ada").id == 1
        with pytest.raises(orm.DoesNotExist):
            User.objects.get(name="nobody")
        with pytest.raises(orm.MultipleObjectsReturned):
            User.objects.get(age=29)

    @pytest.mark.parametrize("lookup,expected", [
        ({"age__gte": 36}, ["ada", "cy"]),
        ({"age__gt": 36}, ["cy"]),
        ({"age__lte": 29}, ["bob", "eve"]),
        ({"age__lt": 29}, []),
        ({"age__ne": 29}, ["ada", "cy", "dee"]),
        ({"age__in": [29, 41]}, ["bob", "cy", "eve"]),
        ({"name__contains": "d"}, ["ada", "dee"]),
        ({"name__startswith": "c"}, ["cy"]),
        ({"age__isnull": True}, ["dee"]),
        ({"age__isnull": False}, ["ada", "bob", "cy", "eve"]),
        ({"email": ""}, ["bob", "dee"]),
    ])
    def test_lookups(self, users, lookup, expected):
        User, _ = users
        got = [u.name for u in User.objects.filter(**lookup).all()]
        assert got == expected, f"filter({lookup}) gave {got}"

    def test_exclude(self, users):
        User, _ = users
        got = [u.name for u in User.objects.exclude(age=29).all()]
        assert got == ["ada", "cy", "dee"]

    def test_chaining_and_multiple_conditions(self, users):
        User, _ = users
        got = User.objects.filter(age__gte=29).exclude(name__startswith="b").all()
        assert [u.name for u in got] == ["ada", "cy", "eve"]

    def test_chaining_does_not_mutate(self, users):
        User, _ = users
        base = User.objects.filter(age__isnull=False)
        narrowed = base.filter(age__gt=30)
        assert base.count() == 4, "filter() must return a new QuerySet"
        assert narrowed.count() == 2

    def test_unknown_field_and_lookup(self, users):
        User, _ = users
        with pytest.raises(orm.FieldError):
            User.objects.filter(nope=1)
        with pytest.raises(orm.FieldError):
            User.objects.filter(age__wat=1)
        with pytest.raises(orm.FieldError):
            User.objects.order_by("nope")

    def test_order_by(self, users):
        User, _ = users
        assert [u.name for u in User.objects.order_by("name").all()] == [
            "ada", "bob", "cy", "dee", "eve"
        ]
        assert [u.name for u in User.objects.order_by("-name").all()] == [
            "eve", "dee", "cy", "bob", "ada"
        ]

    def test_order_by_multiple_keys_mixed_direction(self, users):
        User, _ = users
        got = [u.name for u in User.objects.filter(age__isnull=False)
               .order_by("age", "-name").all()]
        assert got == ["eve", "bob", "ada", "cy"], got

    def test_none_sorts_first(self, users):
        User, _ = users
        got = [u.name for u in User.objects.order_by("age").all()]
        assert got[0] == "dee", f"None should sort before any value, got {got}"

    def test_limit_and_offset(self, users):
        User, _ = users
        assert [u.name for u in User.objects.order_by("name").limit(2).all()] == [
            "ada", "bob"
        ]
        assert [u.name for u in User.objects.order_by("name").offset(3).all()] == [
            "dee", "eve"
        ]
        assert [u.name for u in User.objects.order_by("name").offset(1).limit(2).all()] == [
            "bob", "cy"
        ]

    def test_count_and_exists(self, users):
        User, _ = users
        assert User.objects.count() == 5
        assert User.objects.filter(age=29).count() == 2
        assert User.objects.filter(age=29).exists() is True
        assert User.objects.filter(age=999).exists() is False


# ---------------------------------------------------------------------------
# QuerySet protocol
# ---------------------------------------------------------------------------
class TestQuerySetProtocol:
    def test_len_iter_index(self, users):
        User, _ = users
        qs = User.objects.order_by("name")
        assert len(qs) == 5
        assert [u.name for u in qs] == ["ada", "bob", "cy", "dee", "eve"]
        assert qs[0].name == "ada"
        assert qs[-1].name == "eve"

    def test_slicing_returns_a_lazy_queryset(self, users):
        User, _ = users
        qs = User.objects.order_by("name")[1:3]
        assert isinstance(qs, orm.QuerySet), "a slice should stay lazy"
        assert [u.name for u in qs.all()] == ["bob", "cy"]

    def test_queryset_is_lazy(self, users):
        User, rows = users
        qs = User.objects.filter(age__gte=0)
        User(id=99, name="late", age=1).save()
        assert any(u.name == "late" for u in qs.all()), (
            "the QuerySet must read storage at evaluation time, not at construction"
        )

    def test_reevaluates_each_time(self, users):
        User, _ = users
        qs = User.objects.filter(name="ada")
        assert qs.count() == 1
        User.objects.get(name="ada").delete()
        assert qs.count() == 0, "a QuerySet should not cache its result set"
