import unittest
from collections.abc import MutableSequence, Sequence

from revisionstore import (
    RevisionList,
    RevisionListView,
    RevisionStatus,
    RevisionStore,
)


class TestRevisionList(unittest.TestCase):
    collection: RevisionList

    def setUp(self) -> None:
        """
        Initialize an empty sequence.
        """

        self.collection = RevisionList()

    def test_protocol(self) -> None:
        """
        Test that the sequence protocol is implemented in full.
        """

        self.assertIsInstance(self.collection, Sequence)
        self.assertIsInstance(self.collection, MutableSequence)

    def test_append_and_get(self) -> None:
        """
        Test appending and subscript access.
        """

        self.collection.append("a")
        self.collection.append("b")

        self.assertEqual(self.collection[0], "a")
        self.assertEqual(self.collection[1], "b")
        self.assertEqual(len(self.collection), 2)

    def test_negative_index(self) -> None:
        """
        Test that a negative position counts from the end.
        """

        self.collection.extend(["a", "b", "c"])

        self.assertEqual(self.collection[-1], "c")
        self.assertEqual(self.collection[-3], "a")

        with self.assertRaises(IndexError):
            self.collection[-4]

    def test_out_of_range(self) -> None:
        """
        Test that a position beyond the end is rejected.
        """

        self.collection.append("a")

        with self.assertRaises(IndexError):
            self.collection[1]

        with self.assertRaises(IndexError):
            self.collection[1] = "b"

        with self.assertRaises(IndexError):
            del self.collection[1]

    def test_set(self) -> None:
        """
        Test assignment to a position.
        """

        self.collection.extend(["a", "b"])
        self.collection[0] = "z"

        self.assertEqual(list(self.collection), ["z", "b"])

    def test_insert_shifts(self) -> None:
        """
        Test that insertion renumbers the positions that follow.
        """

        self.collection.extend(["a", "b"])
        self.collection.insert(0, "z")

        self.assertEqual(list(self.collection), ["z", "a", "b"])
        self.assertEqual(len(self.collection), 3)

    def test_insert_clamps(self) -> None:
        """
        Test that a position out of range is clamped, as a list does.
        """

        self.collection.extend(["a", "b"])
        self.collection.insert(99, "z")
        self.collection.insert(-99, "y")

        self.assertEqual(list(self.collection), ["y", "a", "b", "z"])

    def test_delete_shifts(self) -> None:
        """
        Test that deletion renumbers the positions that follow.
        """

        self.collection.extend(["a", "b", "c"])

        del self.collection[0]

        self.assertEqual(list(self.collection), ["b", "c"])
        self.assertEqual(len(self.collection), 2)

    def test_pop_and_remove(self) -> None:
        """
        Test that the mixins of the protocol work on top of the primitives.
        """

        self.collection.extend(["a", "b", "c"])

        self.assertEqual(self.collection.pop(), "c")
        self.assertEqual(self.collection.pop(0), "a")

        self.collection.remove("b")

        self.assertEqual(list(self.collection), [])

    def test_reverse(self) -> None:
        """
        Test that the sequence can be reversed in place.
        """

        self.collection.extend(["a", "b", "c"])
        self.collection.reverse()

        self.assertEqual(list(self.collection), ["c", "b", "a"])

    def test_index_and_count(self) -> None:
        """
        Test the search mixins of the protocol.
        """

        self.collection.extend(["a", "b", "a"])

        self.assertEqual(self.collection.index("b"), 1)
        self.assertEqual(self.collection.count("a"), 2)
        self.assertIn("a", self.collection)

    def test_slice_read(self) -> None:
        """
        Test that a slice yields a plain list.
        """

        self.collection.extend(["a", "b", "c"])

        self.assertEqual(self.collection[0:2], ["a", "b"])
        self.assertEqual(self.collection[::-1], ["c", "b", "a"])
        self.assertIsInstance(self.collection[0:2], list)

    def test_slice_assignment(self) -> None:
        """
        Test that a slice can be assigned, including a change of length.
        """

        self.collection.extend(["a", "b", "c"])
        self.collection[0:2] = ["x", "y", "z"]

        self.assertEqual(list(self.collection), ["x", "y", "z", "c"])

        self.collection[1:3] = []

        self.assertEqual(list(self.collection), ["x", "c"])

    def test_slice_deletion(self) -> None:
        """
        Test that a slice can be deleted.
        """

        self.collection.extend(["a", "b", "c", "d"])

        del self.collection[1:3]

        self.assertEqual(list(self.collection), ["a", "d"])

    def test_at_reads_history(self) -> None:
        """
        Test that a past revision reports the values of that revision.
        """

        self.collection.extend(["a", "b"])
        self.collection.commit()
        self.collection.append("c")
        self.collection.commit()

        self.assertEqual(list(self.collection.at(1)), ["a", "b"])
        self.assertEqual(list(self.collection.at(2)), ["a", "b", "c"])

    def test_at_reads_history_after_a_shift(self) -> None:
        """
        Test that a past revision survives a deletion that renumbers.
        """

        self.collection.extend(["a", "b", "c"])
        self.collection.commit()

        del self.collection[0]

        self.collection.commit()

        self.assertEqual(list(self.collection.at(1)), ["a", "b", "c"])
        self.assertEqual(list(self.collection.at(2)), ["b", "c"])

    def test_diff_reports_every_renumbered_position(self) -> None:
        """
        Test that a deletion reports each renumbered position as changed.

        This is inherent to keying by position. Removing the first of three
        values rewrites positions zero and one, and leaves position two
        present in the first revision alone. The status is relative to that
        first revision, so position two reports as added rather than removed.
        """

        self.collection.extend(["a", "b", "c"])
        self.collection.commit()

        del self.collection[0]

        self.collection.commit()

        self.assertEqual(dict(self.collection.diff(1, 2)), {0: 0, 1: 0, 2: 1})

    def test_diff_yields_status_members(self) -> None:
        """
        Test that a difference reports members of the enumeration.
        """

        self.collection.extend(["a", "b"])
        self.collection.commit()
        self.collection.append("c")
        self.collection.commit()

        statuses = dict(self.collection.diff(1, 2))

        self.assertEqual(statuses, {2: RevisionStatus.REMOVED})
        self.assertIsInstance(statuses[2], RevisionStatus)

    def test_repr(self) -> None:
        """
        Test the representation of a sequence.
        """

        self.collection.append("a")

        self.assertEqual(repr(self.collection), "RevisionList(revision=1, values=1)")

    def test_wraps_a_given_store(self) -> None:
        """
        Test that a sequence can be constructed around an existing store.
        """

        store = RevisionStore()
        collection = RevisionList(store)

        collection.append("a")

        self.assertIs(collection.store, store)
        self.assertEqual(store.get(0), "a")


class TestRevisionListView(unittest.TestCase):
    collection: RevisionList

    def setUp(self) -> None:
        """
        Initialize a sequence with two committed revisions.
        """

        self.collection = RevisionList()
        self.collection.extend(["a", "b"])
        self.collection.commit()
        self.collection.append("c")
        self.collection.commit()

    def test_protocol(self) -> None:
        """
        Test that a view is a read-only sequence.
        """

        view = self.collection.at(1)

        self.assertIsInstance(view, RevisionListView)
        self.assertIsInstance(view, Sequence)
        self.assertNotIsInstance(view, MutableSequence)

    def test_contents(self) -> None:
        """
        Test the contents of a view.
        """

        view = self.collection.at(1)

        self.assertEqual(list(view), ["a", "b"])
        self.assertEqual(len(view), 2)
        self.assertEqual(view[0], "a")
        self.assertEqual(view[-1], "b")
        self.assertIn("a", view)

    def test_slice(self) -> None:
        """
        Test that a view can be sliced.
        """

        view = self.collection.at(2)

        self.assertEqual(view[0:2], ["a", "b"])
        self.assertEqual(view[::-1], ["c", "b", "a"])

    def test_out_of_range(self) -> None:
        """
        Test that a position beyond the end of a view is rejected.
        """

        view = self.collection.at(1)

        with self.assertRaises(IndexError):
            view[2]

        with self.assertRaises(IndexError):
            view[-3]

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

    def test_repr(self) -> None:
        """
        Test the representation of a view.
        """

        self.assertEqual(repr(self.collection.at(1)), "RevisionListView(revision=1)")

    def test_is_a_window(self) -> None:
        """
        Test that a view is not affected by later revisions.
        """

        view = self.collection.at(1)

        self.collection.append("d")
        self.collection.commit()

        self.assertEqual(list(view), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
