import pickle
import unittest
from collections.abc import Mapping, MutableMapping
from typing import Any

from revisionstore import (
    RevisionDict,
    RevisionDictView,
    RevisionStatus,
    RevisionStore,
)


class TestRevisionDict(unittest.TestCase):
    mapping: RevisionDict

    def setUp(self) -> None:
        """
        Initialize an empty mapping.
        """

        self.mapping = RevisionDict()

    def test_protocol(self) -> None:
        """
        Test that the mapping protocol is implemented in full.
        """

        self.assertIsInstance(self.mapping, Mapping)
        self.assertIsInstance(self.mapping, MutableMapping)

    def test_set_and_get(self) -> None:
        """
        Test assignment and subscript access.
        """

        self.mapping["a"] = 1
        self.mapping["b"] = 2

        self.assertEqual(self.mapping["a"], 1)
        self.assertEqual(self.mapping["b"], 2)

        self.mapping["a"] = 3

        self.assertEqual(self.mapping["a"], 3)

        with self.assertRaises(KeyError):
            self.mapping["c"]

    def test_delete(self) -> None:
        """
        Test deletion, including of keys that are not present.
        """

        self.mapping["a"] = 1

        del self.mapping["a"]

        self.assertNotIn("a", self.mapping)

        with self.assertRaises(KeyError):
            del self.mapping["a"]

        with self.assertRaises(KeyError):
            del self.mapping["never-existed"]

    def test_len(self) -> None:
        """
        Test that the length reflects the current revision.
        """

        self.assertEqual(len(self.mapping), 0)

        self.mapping["a"] = 1
        self.mapping["b"] = 2

        self.assertEqual(len(self.mapping), 2)

        self.mapping["a"] = 3

        self.assertEqual(len(self.mapping), 2)

        del self.mapping["a"]

        self.assertEqual(len(self.mapping), 1)

    def test_iteration_yields_keys_in_insertion_order(self) -> None:
        """
        Test that iteration yields keys, in the order a dictionary would.
        """

        self.mapping["a"] = 1
        self.mapping["b"] = 2
        self.mapping["c"] = 3

        self.assertListEqual(list(self.mapping), ["a", "b", "c"])
        self.assertListEqual(list(self.mapping.keys()), ["a", "b", "c"])
        self.assertListEqual(list(self.mapping.values()), [1, 2, 3])
        self.assertListEqual(list(self.mapping.items()), [("a", 1), ("b", 2), ("c", 3)])

        # Replacing a value keeps the position of the key.
        self.mapping["a"] = 9

        self.assertListEqual(list(self.mapping), ["a", "b", "c"])

        del self.mapping["b"]

        self.assertListEqual(list(self.mapping), ["a", "c"])

    def test_contains(self) -> None:
        """
        Test that membership is decided on keys.
        """

        self.mapping["a"] = 1

        self.assertIn("a", self.mapping)
        self.assertNotIn("b", self.mapping)

        del self.mapping["a"]

        self.assertNotIn("a", self.mapping)

    def test_get_follows_dict_semantics(self) -> None:
        """
        Test that get returns a default rather than raising.
        """

        self.mapping["a"] = 1

        self.assertEqual(self.mapping.get("a"), 1)
        self.assertIsNone(self.mapping.get("b"))
        self.assertEqual(self.mapping.get("b", "default"), "default")

    def test_conversion_to_dict(self) -> None:
        """
        Test that the mapping converts and unpacks like a dictionary.
        """

        self.mapping["a"] = 1
        self.mapping["b"] = 2

        self.assertDictEqual(dict(self.mapping), {"a": 1, "b": 2})
        self.assertDictEqual({**self.mapping}, {"a": 1, "b": 2})

    def test_mixin_methods(self) -> None:
        """
        Test the methods that the mapping protocol derives.
        """

        self.mapping.update({"a": 1, "b": 2})

        self.assertDictEqual(dict(self.mapping), {"a": 1, "b": 2})

        self.assertEqual(self.mapping.pop("a"), 1)
        self.assertNotIn("a", self.mapping)
        self.assertEqual(self.mapping.pop("a", "default"), "default")

        self.assertEqual(self.mapping.setdefault("c", 3), 3)
        self.assertEqual(self.mapping["c"], 3)
        self.assertEqual(self.mapping.setdefault("c", 4), 3)

        self.mapping.clear()

        self.assertEqual(len(self.mapping), 0)
        self.assertListEqual(list(self.mapping), [])

    def test_revision_properties(self) -> None:
        """
        Test that the revision bookkeeping is exposed.
        """

        self.assertEqual(self.mapping.revision, 1)
        self.assertEqual(self.mapping.min_revision, 1)

        self.mapping.commit()

        self.assertEqual(self.mapping.revision, 2)

        self.mapping.commit(revision=5)

        self.assertEqual(self.mapping.revision, 5)

    def test_history_through_at(self) -> None:
        """
        Test that past revisions are reachable and unaffected by later ones.
        """

        self.mapping["a"] = "a1"
        self.mapping["b"] = "b1"
        self.mapping.commit()

        self.mapping["a"] = "a2"
        self.mapping.commit()

        del self.mapping["b"]

        self.assertDictEqual(dict(self.mapping), {"a": "a2"})
        self.assertDictEqual(dict(self.mapping.at(1)), {"a": "a1", "b": "b1"})
        self.assertDictEqual(dict(self.mapping.at(2)), {"a": "a2", "b": "b1"})
        self.assertDictEqual(dict(self.mapping.at(3)), {"a": "a2"})
        self.assertDictEqual(dict(self.mapping.at()), {"a": "a2"})

    def test_diff(self) -> None:
        """
        Test that diffing is delegated to the store.
        """

        self.mapping.commit()
        self.mapping["a"] = "a2"
        self.mapping.commit()
        del self.mapping["a"]

        self.assertListEqual(list(self.mapping.diff(3, 2)), [("a", -1)])
        self.assertListEqual(list(self.mapping.diff(2, 3)), [("a", 1)])

    def test_clean(self) -> None:
        """
        Test that cleaning is delegated to the store.
        """

        self.mapping["a"] = "a1"
        self.mapping.commit()
        self.mapping["a"] = "a2"

        self.assertEqual(self.mapping.at(1)["a"], "a1")

        self.mapping.clean()

        self.assertEqual(self.mapping.min_revision, 2)

        with self.assertRaises(ValueError):
            self.mapping.at(1)

    def test_wraps_existing_store(self) -> None:
        """
        Test that a mapping can be built around an existing store.
        """

        store = RevisionStore()
        store.add("a", 1)

        mapping = RevisionDict(store)

        self.assertIs(mapping.store, store)
        self.assertEqual(mapping["a"], 1)

        # Both interfaces address the same data.
        mapping["b"] = 2

        self.assertEqual(store.get("b"), 2)
        self.assertEqual(len(store), 2)

    def test_diff_yields_status_members(self) -> None:
        """
        Test that a difference reports members of the enumeration.
        """

        self.mapping["a"] = 1
        self.mapping.commit()
        self.mapping["a"] = 2
        self.mapping.commit()

        statuses = dict(self.mapping.diff(1, 2))

        self.assertEqual(statuses, {"a": RevisionStatus.CHANGED})
        self.assertIsInstance(statuses["a"], RevisionStatus)

    def test_repr(self) -> None:
        """
        Test the representation of the mapping.
        """

        self.assertEqual(repr(self.mapping), "RevisionDict(revision=1, keys=0)")

        self.mapping["a"] = 1

        self.assertEqual(repr(self.mapping), "RevisionDict(revision=1, keys=1)")

    def test_keys_of_any_hashable_type(self) -> None:
        """
        Test that keys are not restricted to strings.
        """

        key: tuple[int, int] = (1, 2)

        self.mapping[key] = "value"
        self.mapping[7] = "seven"

        self.assertEqual(self.mapping[key], "value")
        self.assertEqual(self.mapping[7], "seven")
        self.assertIn(key, self.mapping)

    def test_pickling_a_value(self) -> None:
        """
        Test that arbitrary values survive a round trip.
        """

        value: dict[str, Any] = {"nested": [1, 2, 3]}

        self.mapping["a"] = value

        self.assertEqual(pickle.loads(pickle.dumps(self.mapping["a"])), value)


class TestRevisionDictView(unittest.TestCase):
    mapping: RevisionDict

    def setUp(self) -> None:
        """
        Initialize a mapping with two committed revisions.
        """

        self.mapping = RevisionDict()
        self.mapping["a"] = "a1"
        self.mapping["b"] = "b1"
        self.mapping.commit()
        self.mapping["a"] = "a2"

    def test_protocol(self) -> None:
        """
        Test that a view is a read-only mapping.
        """

        view = self.mapping.at(1)

        self.assertIsInstance(view, Mapping)
        self.assertNotIsInstance(view, MutableMapping)

        with self.assertRaises(TypeError):
            view["a"] = "nope"  # type: ignore[index]

    def test_reads(self) -> None:
        """
        Test reading a past revision through a view.
        """

        view: RevisionDictView = self.mapping.at(1)

        self.assertEqual(view.revision, 1)
        self.assertEqual(view["a"], "a1")
        self.assertEqual(len(view), 2)
        self.assertIn("a", view)
        self.assertNotIn("c", view)
        self.assertListEqual(list(view), ["a", "b"])
        self.assertDictEqual(dict(view), {"a": "a1", "b": "b1"})
        self.assertEqual(view.get("c", "default"), "default")

        with self.assertRaises(KeyError):
            view["c"]

    def test_out_of_bounds(self) -> None:
        """
        Test that an unreachable revision is rejected immediately.
        """

        with self.assertRaises(ValueError):
            self.mapping.at(99)

    def test_repr(self) -> None:
        """
        Test the representation of a view.
        """

        self.assertEqual(repr(self.mapping.at(1)), "RevisionDictView(revision=1)")
