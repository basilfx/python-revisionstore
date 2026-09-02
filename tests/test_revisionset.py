import pickle
import unittest
from collections.abc import MutableSet, Set

from revisionstore import (
    RevisionSet,
    RevisionSetView,
    RevisionStatus,
    RevisionStore,
)


class TestRevisionSet(unittest.TestCase):
    collection: RevisionSet

    def setUp(self) -> None:
        """
        Initialize an empty set.
        """

        self.collection = RevisionSet()

    def test_protocol(self) -> None:
        """
        Test that the set protocol is implemented in full.
        """

        self.assertIsInstance(self.collection, Set)
        self.assertIsInstance(self.collection, MutableSet)

    def test_add_and_contains(self) -> None:
        """
        Test addition and membership.
        """

        self.collection.add("a")
        self.collection.add("b")

        self.assertIn("a", self.collection)
        self.assertIn("b", self.collection)
        self.assertNotIn("c", self.collection)
        self.assertEqual(len(self.collection), 2)

    def test_add_is_idempotent(self) -> None:
        """
        Test that adding a present element does not extend its history.
        """

        self.collection.add("a")

        entry = self.collection.store.lookup["a"]

        self.collection.add("a")

        self.assertIs(self.collection.store.lookup["a"], entry)
        self.assertEqual(len(self.collection), 1)

    def test_discard_and_remove(self) -> None:
        """
        Test that discarding is silent and removing is not.
        """

        self.collection.add("a")
        self.collection.discard("a")
        self.collection.discard("a")

        self.assertNotIn("a", self.collection)
        self.assertEqual(len(self.collection), 0)

        with self.assertRaises(KeyError):
            self.collection.remove("a")

    def test_readd_after_discard(self) -> None:
        """
        Test that an element can be added again after it was discarded.
        """

        self.collection.add("a")
        self.collection.discard("a")
        self.collection.add("a")

        self.assertIn("a", self.collection)
        self.assertEqual(len(self.collection), 1)

    def test_iteration_order(self) -> None:
        """
        Test that elements are yielded in order of first insertion.
        """

        for element in ("c", "a", "b"):
            self.collection.add(element)

        self.assertEqual(list(self.collection), ["c", "a", "b"])

    def test_operators_return_plain_sets(self) -> None:
        """
        Test that the set operators produce a plain set.
        """

        self.collection.add("a")
        self.collection.add("b")

        union = self.collection | {"c"}

        self.assertIsInstance(union, set)
        self.assertEqual(union, {"a", "b", "c"})
        self.assertEqual(self.collection & {"a"}, {"a"})
        self.assertEqual(self.collection - {"a"}, {"b"})

    def test_at_reads_history(self) -> None:
        """
        Test that a past revision reports the elements of that revision.
        """

        self.collection.add("a")
        self.collection.commit()
        self.collection.add("b")
        self.collection.discard("a")
        self.collection.commit()

        self.assertEqual(set(self.collection.at(1)), {"a"})
        self.assertEqual(set(self.collection.at(2)), {"b"})

    def test_diff(self) -> None:
        """
        Test that a difference reports the elements that changed.
        """

        self.collection.add("a")
        self.collection.commit()
        self.collection.add("b")
        self.collection.discard("a")
        self.collection.commit()

        self.assertEqual(dict(self.collection.diff(1, 2)), {"a": 1, "b": -1})

    def test_diff_yields_status_members(self) -> None:
        """
        Test that a difference reports members of the enumeration.
        """

        self.collection.add("a")
        self.collection.commit()
        self.collection.add("b")
        self.collection.discard("a")
        self.collection.commit()

        statuses = dict(self.collection.diff(1, 2))

        self.assertEqual(
            statuses,
            {"a": RevisionStatus.ADDED, "b": RevisionStatus.REMOVED},
        )
        self.assertIsInstance(statuses["a"], RevisionStatus)

    def test_repr(self) -> None:
        """
        Test the representation of a set.
        """

        self.collection.add("a")

        self.assertEqual(repr(self.collection), "RevisionSet(revision=1, elements=1)")

    def test_pickle_of_element(self) -> None:
        """
        Test that a stored element survives a round trip through pickle.
        """

        value = {"a": [1, 2, 3]}

        self.collection.add("a")

        self.assertEqual(pickle.loads(pickle.dumps(value)), value)


class TestRevisionSetView(unittest.TestCase):
    collection: RevisionSet

    def setUp(self) -> None:
        """
        Initialize a set with two committed revisions.
        """

        self.collection = RevisionSet()
        self.collection.add("a")
        self.collection.commit()
        self.collection.add("b")
        self.collection.commit()

    def test_protocol(self) -> None:
        """
        Test that a view is a read-only set.
        """

        view = self.collection.at(1)

        self.assertIsInstance(view, RevisionSetView)
        self.assertIsInstance(view, Set)
        self.assertNotIsInstance(view, MutableSet)

    def test_contents(self) -> None:
        """
        Test the contents of a view.
        """

        view = self.collection.at(1)

        self.assertEqual(set(view), {"a"})
        self.assertEqual(len(view), 1)
        self.assertIn("a", view)
        self.assertNotIn("b", view)

    def test_properties(self) -> None:
        """
        Test that a view exposes its revision and store.
        """

        view = self.collection.at(1)

        self.assertEqual(view.revision, 1)
        self.assertIs(view.store, self.collection.store)

    def test_default_revision(self) -> None:
        """
        Test that a view defaults to the revision that is currently open.
        """

        self.assertEqual(self.collection.at().revision, 3)

    def test_out_of_bounds(self) -> None:
        """
        Test that a view of an unknown revision is rejected.
        """

        with self.assertRaises(ValueError):
            self.collection.at(99)

    def test_operators_return_plain_sets(self) -> None:
        """
        Test that the operators of a view produce a plain set.
        """

        view = self.collection.at(1)

        self.assertIsInstance(view | {"z"}, set)
        self.assertEqual(view | {"z"}, {"a", "z"})

    def test_repr(self) -> None:
        """
        Test the representation of a view.
        """

        self.assertEqual(repr(self.collection.at(1)), "RevisionSetView(revision=1)")

    def test_is_a_window(self) -> None:
        """
        Test that a view is not affected by later revisions.
        """

        view = self.collection.at(1)

        self.collection.add("c")
        self.collection.commit()

        self.assertEqual(set(view), {"a"})


class TestRevisionSetStore(unittest.TestCase):
    def test_wraps_a_given_store(self) -> None:
        """
        Test that a set can be constructed around an existing store.
        """

        store = RevisionStore()
        collection = RevisionSet(store)

        collection.add("a")

        self.assertIs(collection.store, store)
        self.assertIn("a", store)

    def test_element_is_its_own_value(self) -> None:
        """
        Test that an element is stored as its own value.
        """

        collection = RevisionSet()
        collection.add("a")

        self.assertEqual(collection.store.get("a"), "a")


if __name__ == "__main__":
    unittest.main()
