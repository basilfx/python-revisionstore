import unittest
from collections.abc import Iterable
from typing import Any

from revisionstore import RevisionStatus, RevisionStore


class TestRevisionStore(unittest.TestCase):
    store: RevisionStore

    def assert_iter_equal(self, actual: Iterable[Any], expected: list[Any]) -> None:
        """
        Assert that an iterable yields the expected items, in order.
        """

        self.assertListEqual(list(actual), expected)

    def setUp(self) -> None:
        """
        Initialize an empty revision store.
        """

        self.store = RevisionStore()

    def test_add(self) -> None:
        """
        Test basic add functionality.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1", "A1"])

        self.store.add("A", "A2")
        self.store.add("D", "D1")

        self.assert_iter_equal(self.store.iterate(), ["D1", "C1", "B1", "A2"])

    def test_remove(self) -> None:
        """
        Test basic remove functionality.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1", "A1"])

        self.store.remove("A")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1"])

        self.store.remove("C")

        self.assert_iter_equal(self.store.iterate(), ["B1"])

    def test_remove_fail(self) -> None:
        """
        Test that removing an unknown key fails.
        """

        with self.assertRaises(KeyError):
            self.store.remove("A")

    def test_get(self) -> None:
        """
        Test basic get functionality.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assertEqual(self.store.get("A"), "A1")
        self.assertEqual(self.store.get("A", revision=1), "A1")

        self.store.commit()
        self.store.add("A", "A2")

        self.assertEqual(self.store.get("A"), "A2")
        self.assertEqual(self.store.get("A", revision=2), "A2")
        self.assertEqual(self.store.get("A", revision=1), "A1")

        self.store.commit()
        self.store.remove("A")

        with self.assertRaises(KeyError):
            self.store.get("A")

        self.assertEqual(self.store.get("A", revision=2), "A2")
        self.assertEqual(self.store.get("A", revision=1), "A1")

    def test_get_fail(self) -> None:
        """
        Test edge cases for get functionality.
        """

        self.store.add("A", "A1")
        self.store.remove("A")

        with self.assertRaises(KeyError):
            self.store.get("A", revision=1)

    def test_get_unknown_key(self) -> None:
        """
        Test that getting an unknown key fails.
        """

        with self.assertRaises(KeyError):
            self.store.get("A")

        with self.assertRaises(KeyError):
            self.store.get("A", revision=1)

    def test_get_before_add(self) -> None:
        """
        Test that getting a key before it was added fails.
        """

        self.store.commit()
        self.store.add("A", "A2")

        with self.assertRaises(KeyError):
            self.store.get("A", revision=1)

    def test_commit(self) -> None:
        """
        Test commit and revision functionality.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assertEqual(self.store.revision, 1)
        self.assert_iter_equal(self.store.iterate(), ["C1", "B1", "A1"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["C1", "B1", "A1"])

        self.store.commit()
        self.store.add("A", "A2")
        self.store.add("D", "D1")

        self.assertEqual(self.store.revision, 2)
        self.assert_iter_equal(self.store.iterate(), ["D1", "C1", "B1", "A2"])
        self.assert_iter_equal(self.store.iterate(revision=2), ["D1", "C1", "B1", "A2"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["C1", "B1", "A1"])

        self.store.commit()
        self.store.remove("A")
        self.store.remove("C")

        self.assertEqual(self.store.revision, 3)
        self.assert_iter_equal(self.store.iterate(), ["D1", "B1"])
        self.assert_iter_equal(self.store.iterate(revision=3), ["D1", "B1"])
        self.assert_iter_equal(self.store.iterate(revision=2), ["D1", "C1", "B1", "A2"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["C1", "B1", "A1"])

    def test_commit_to_revision(self) -> None:
        """
        Test committing to an explicit revision.
        """

        self.store.add("A", "A1")
        self.store.commit(revision=5)

        self.assertEqual(self.store.revision, 5)

        self.store.add("B", "B5")

        self.assert_iter_equal(self.store.iterate(revision=5), ["B5", "A1"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["A1"])

    def test_commit_to_lower_or_equal_revision_fails(self) -> None:
        """
        Test that committing to a revision lower than or equal to the current
        one fails.
        """

        self.store.commit(revision=3)

        with self.assertRaises(ValueError):
            self.store.commit(revision=2)

        with self.assertRaises(ValueError):
            self.store.commit(revision=3)

    def test_iterate(self) -> None:
        """
        Test iteration over an explicit revision.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1", "A1"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["C1", "B1", "A1"])
        self.assert_iter_equal(self.store.iterate(revision=-1), ["C1", "B1", "A1"])

        with self.assertRaises(ValueError):
            for _ in self.store.iterate(revision=2):
                pass

    def test_clean(self) -> None:
        """
        Test that cleaning discards the history up to a revision.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1", "A1"])

        self.store.commit()
        self.store.remove("A")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1"])
        self.assert_iter_equal(self.store.iterate(revision=2), ["C1", "B1"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["C1", "B1", "A1"])

        self.store.commit()
        self.store.remove("C")

        self.assert_iter_equal(self.store.iterate(), ["B1"])
        self.assert_iter_equal(self.store.iterate(revision=3), ["B1"])
        self.assert_iter_equal(self.store.iterate(revision=2), ["C1", "B1"])
        self.assert_iter_equal(self.store.iterate(revision=1), ["C1", "B1", "A1"])

        self.store.clean(revision=2)

        self.assertEqual(self.store.min_revision, 2)
        self.assert_iter_equal(self.store.iterate(), ["B1"])
        self.assert_iter_equal(self.store.iterate(revision=3), ["B1"])
        self.assert_iter_equal(self.store.iterate(revision=2), ["C1", "B1"])

        with self.assertRaises(ValueError):
            for _ in self.store.iterate(revision=1):
                pass

        self.store.clean()

        self.assertEqual(self.store.min_revision, 3)
        self.assert_iter_equal(self.store.iterate(), ["B1"])
        self.assert_iter_equal(self.store.iterate(revision=3), ["B1"])

        with self.assertRaises(ValueError):
            for _ in self.store.iterate(revision=2):
                pass

    def test_diff(self) -> None:
        """
        Test diff functionality (1).
        """

        self.store.commit()
        self.store.add("A", "A2")
        self.store.commit()
        self.store.remove("A")

        self.assert_iter_equal(self.store.diff(3, 1), [("A", 1)])
        self.assert_iter_equal(self.store.diff(1, 3), [("A", -1)])

        self.assert_iter_equal(self.store.diff(2, 1), [("A", 1)])
        self.assert_iter_equal(self.store.diff(1, 2), [("A", -1)])

        self.assert_iter_equal(self.store.diff(3, 2), [("A", -1)])
        self.assert_iter_equal(self.store.diff(2, 3), [("A", 1)])

    def test_diff2(self) -> None:
        """
        Test diff functionality (2).
        """

        self.store.commit()
        self.store.add("A", "A2")
        self.store.commit()
        self.store.remove("A")
        self.store.commit()
        self.store.add("B", "B4")
        self.store.commit()
        self.store.add("C", "C5")
        self.store.commit()
        self.store.remove("B")

        self.assert_iter_equal(self.store.diff(6, 5), [("B", -1)])
        self.assert_iter_equal(self.store.diff(5, 6), [("B", 1)])

    def test_diff3(self) -> None:
        """
        Test diff functionality (3).
        """

        self.store.commit()
        self.store.add("A", "A2")
        self.store.commit()
        self.store.add("B", "B3")
        self.store.commit()
        self.store.add("C", "C4")

        self.assert_iter_equal(self.store.diff(4, 3), [("C", 1)])
        self.assert_iter_equal(self.store.diff(3, 4), [("C", -1)])

    def test_diff4(self) -> None:
        """
        Test diff functionality (4).
        """

        self.store.commit()
        self.store.add("A", "A2.1")
        self.store.add("A", "A2.2")
        self.store.commit()
        self.store.remove("A")
        self.store.commit()
        self.store.add("A", "A4")
        self.store.commit()
        self.store.remove("A")
        self.store.commit()
        self.store.add("A", "A6")
        self.store.commit()
        self.store.commit()
        self.store.add("A", "A8")

        self.assert_iter_equal(self.store.diff(8, 7), [("A", 0)])
        self.assert_iter_equal(self.store.diff(8, 6), [("A", 0)])
        self.assert_iter_equal(self.store.diff(8, 5), [("A", 1)])
        self.assert_iter_equal(self.store.diff(8, 4), [("A", 0)])
        self.assert_iter_equal(self.store.diff(8, 3), [("A", 1)])
        self.assert_iter_equal(self.store.diff(8, 2), [("A", 0)])
        self.assert_iter_equal(self.store.diff(8, 1), [("A", 1)])

        self.assert_iter_equal(self.store.diff(7, 8), [("A", 0)])
        self.assert_iter_equal(self.store.diff(6, 8), [("A", 0)])
        self.assert_iter_equal(self.store.diff(5, 8), [("A", -1)])
        self.assert_iter_equal(self.store.diff(4, 8), [("A", 0)])
        self.assert_iter_equal(self.store.diff(3, 8), [("A", -1)])
        self.assert_iter_equal(self.store.diff(2, 8), [("A", 0)])
        self.assert_iter_equal(self.store.diff(1, 8), [("A", -1)])

        self.assert_iter_equal(self.store.diff(5, 2), [("A", -1)])
        self.assert_iter_equal(self.store.diff(2, 5), [("A", 1)])

        self.assert_iter_equal(self.store.diff(8, 8), [("A", 1)])
        self.assert_iter_equal(self.store.diff(5, 5), [])
        self.assert_iter_equal(self.store.diff(4, 4), [("A", 1)])
        self.assert_iter_equal(self.store.diff(3, 3), [])
        self.assert_iter_equal(self.store.diff(1, 1), [])

    def test_diff_fail(self) -> None:
        """
        Test that diffing an out of bounds revision fails.
        """

        self.store.add("A", "A1")

        with self.assertRaises(ValueError):
            for _ in self.store.diff(1, 2):
                pass

        with self.assertRaises(ValueError):
            for _ in self.store.diff(2, 1):
                pass

    def test_iter(self) -> None:
        """
        Test that the store itself is iterable.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.add("C", "C1")

        self.assert_iter_equal(self.store.iterate(), ["C1", "B1", "A1"])
        self.assert_iter_equal(iter(self.store), ["C1", "B1", "A1"])

        self.store.commit()
        self.store.add("A", "A2")
        self.store.add("D", "D1")

        self.assert_iter_equal(self.store.iterate(), ["D1", "C1", "B1", "A2"])
        self.assert_iter_equal(iter(self.store), ["D1", "C1", "B1", "A2"])

    def test_contains(self) -> None:
        """
        Test the containment check.
        """

        self.assertNotIn("A", self.store)

        self.store.add("A", "A1")

        self.assertIn("A", self.store)
        self.assertNotIn("B", self.store)

        self.store.commit()
        self.store.remove("A")

        self.assertNotIn("A", self.store)

    def test_bool(self) -> None:
        """
        Test coercion to boolean.
        """

        self.assertFalse(self.store)

        self.store.add("A", "A1")

        self.assertTrue(self.store)

        self.store.add("A", "A2")

        self.assertTrue(self.store)

        self.store.remove("A")

        self.assertFalse(self.store)

    def test_repr(self) -> None:
        """
        Test the representation of the store.
        """

        self.assertEqual(repr(self.store), "RevisionStore(min_revision=1, revision=1)")

        self.store.commit()

        self.assertEqual(repr(self.store), "RevisionStore(min_revision=1, revision=2)")

    def test_len(self) -> None:
        """
        Test that the length tracks the keys of the current revision.
        """

        self.assertEqual(len(self.store), 0)

        self.store.add("A", "A1")
        self.store.add("B", "B1")

        self.assertEqual(len(self.store), 2)

        # Replacing a value does not change the number of keys.
        self.store.add("A", "A1.2")

        self.assertEqual(len(self.store), 2)

        self.store.commit()
        self.store.remove("A")

        self.assertEqual(len(self.store), 1)

        # Removing a key that is already removed does not count twice.
        self.store.remove("A")

        self.assertEqual(len(self.store), 1)

        # Adding it back makes it count again.
        self.store.add("A", "A3")

        self.assertEqual(len(self.store), 2)

        self.store.remove("A")
        self.store.remove("B")

        self.assertEqual(len(self.store), 0)

    def test_len_survives_commit_and_clean(self) -> None:
        """
        Test that committing and cleaning leave the length alone.
        """

        self.store.add("A", "A1")
        self.store.add("B", "B1")
        self.store.commit()

        self.assertEqual(len(self.store), 2)

        self.store.remove("A")
        self.store.commit()
        self.store.clean()

        self.assertEqual(len(self.store), 1)

    def test_check_revision(self) -> None:
        """
        Test the public revision bounds check.
        """

        self.store.add("A", "A1")
        self.store.commit()

        self.store.check_revision(1)
        self.store.check_revision(2)

        with self.assertRaises(ValueError):
            self.store.check_revision(3)

        self.store.clean(revision=2)

        with self.assertRaises(ValueError):
            self.store.check_revision(1)

    def test_bool_with_leading_tombstones(self) -> None:
        """
        Test coercion when the head of the store is marked as removed.

        The truth of a store is derived from the number of present keys rather
        than from walking the list, so a run of removed entries in front of a
        present one must not affect it.
        """

        self.store.add("keep", "keep1")
        self.store.add("drop1", "drop1")
        self.store.add("drop2", "drop2")
        self.store.commit()
        self.store.remove("drop1")
        self.store.remove("drop2")

        # Both removed keys sit in front of the present one.
        self.assertTrue(self.store)
        self.assertEqual(len(self.store), 1)

        self.store.remove("keep")

        self.assertFalse(self.store)
        self.assertEqual(len(self.store), 0)

    def test_bool_agrees_with_len_and_iteration(self) -> None:
        """
        Test that the three views on emptiness never disagree.

        The length and the truth of a store are both answered from a counter,
        while iteration walks the entries. This asserts the two agree over a
        deterministic pseudo random sequence of operations.
        """

        keys = [f"k{index}" for index in range(8)]
        state = 12345
        present: set[str] = set()

        def rand(modulo: int) -> int:
            nonlocal state

            state = (state * 1103515245 + 12345) & 0x7FFFFFFF

            return state % modulo

        for _ in range(2000):
            key = keys[rand(len(keys))]
            choice = rand(100)

            if choice < 45:
                self.store.add(key, object())
                present.add(key)
            elif choice < 75:
                if key in self.store:
                    self.store.remove(key)
                    present.discard(key)
            elif choice < 92:
                self.store.commit()
            else:
                self.store.clean()

            walked = sum(1 for _ in self.store.iterate())

            self.assertEqual(len(self.store), walked)
            self.assertEqual(len(self.store), len(present))
            self.assertEqual(bool(self.store), walked > 0)


class TestRevisionStoreSince(unittest.TestCase):
    store: RevisionStore

    def setUp(self) -> None:
        """
        Initialize an empty store.
        """

        self.store = RevisionStore()

    def test_since(self) -> None:
        """
        Test that a value reports the revision it was assigned in.
        """

        self.store.add("k", "v1")
        self.store.commit()
        self.store.add("k", "v2")

        self.assertEqual(self.store.since("v1"), 1)
        self.assertEqual(self.store.since("v2"), 2)

    def test_earliest_of_several_keys(self) -> None:
        """
        Test that the oldest revision of a shared value is reported.
        """

        self.store.add("a", "shared")
        self.store.commit()
        self.store.add("b", "shared")
        self.store.commit()

        self.assertEqual(self.store.since("shared"), 1)

    def test_earliest_is_independent_of_insertion_order(self) -> None:
        """
        Test that the order in which keys were added does not matter.
        """

        other = RevisionStore()

        self.store.add("a", "shared")
        self.store.add("b", "other")
        other.add("b", "other")
        other.add("a", "shared")

        for store in (self.store, other):
            store.commit()
            store.add("b", "shared")

        self.assertEqual(self.store.since("shared"), other.since("shared"))

    def test_value_that_returns(self) -> None:
        """
        Test that the first of several occurrences is reported.
        """

        self.store.add("k", "x")
        self.store.commit()
        self.store.remove("k")
        self.store.commit()
        self.store.add("k", "x")

        self.assertEqual(self.store.since("x"), 1)

    def test_unknown_value(self) -> None:
        """
        Test that a value the store never held is rejected.
        """

        self.store.add("k", "v")

        with self.assertRaises(ValueError):
            self.store.since("other")

    def test_tombstone_is_not_a_value(self) -> None:
        """
        Test that an entry marking a key as removed never matches.
        """

        self.store.add("k", "v")
        self.store.commit()
        self.store.remove("k")

        with self.assertRaises(ValueError):
            self.store.since(None)

    def test_value_hidden_within_a_revision(self) -> None:
        """
        Test that a value no revision can report is not found.

        Assigning a key twice within one revision leaves the first value
        unreadable, so it is not an answer that :meth:`since` may give.
        """

        self.store.add("k", "first")
        self.store.add("k", "second")

        self.assertEqual(self.store.since("second"), 1)

        with self.assertRaises(ValueError):
            self.store.since("first")

    def test_matched_on_equality(self) -> None:
        """
        Test that a value is matched on equality rather than identity.
        """

        self.store.add("k", [1, 2, 3])

        self.assertEqual(self.store.since([1, 2, 3]), 1)

    def test_unhashable_value(self) -> None:
        """
        Test that an unhashable value can be looked up.
        """

        self.store.add("k", {"a": 1})

        self.assertEqual(self.store.since({"a": 1}), 1)

    def test_result_can_be_read_back(self) -> None:
        """
        Test that the reported revision is never cleaned away.
        """

        self.store.add("k", "early")
        self.store.commit()
        self.store.commit()
        self.store.clean(3)

        revision = self.store.since("early")

        self.assertGreaterEqual(revision, self.store.min_revision)
        self.assertEqual(self.store.get("k", revision), "early")

    def test_value_cleaned_away(self) -> None:
        """
        Test that a value which no readable revision holds is rejected.

        Cleaning leaves the entry that survives it in place without
        renumbering, so an entry can predate the oldest readable revision.
        Such a value is only reported while it still holds in that revision.
        """

        self.store.add("k", "old")
        self.store.commit()
        self.store.clean(2)
        self.store.add("k", "new")

        self.assertEqual(self.store.since("new"), 2)

        with self.assertRaises(ValueError):
            self.store.since("old")


class TestRevisionStatus(unittest.TestCase):
    store: RevisionStore

    def setUp(self) -> None:
        """
        Initialize a store with two committed revisions.
        """

        self.store = RevisionStore()
        self.store.add("a", 1)
        self.store.add("b", 2)
        self.store.commit()
        self.store.add("b", 3)
        self.store.remove("a")
        self.store.add("c", 4)
        self.store.commit()

    def test_members(self) -> None:
        """
        Test the members of the enumeration.
        """

        self.assertEqual(RevisionStatus.REMOVED, -1)
        self.assertEqual(RevisionStatus.CHANGED, 0)
        self.assertEqual(RevisionStatus.ADDED, 1)
        self.assertEqual(len(RevisionStatus), 3)

    def test_is_an_integer(self) -> None:
        """
        Test that a member is an integer, so that older code keeps working.
        """

        self.assertIsInstance(RevisionStatus.ADDED, int)
        self.assertEqual(int(RevisionStatus.ADDED), 1)

    def test_diff_yields_members(self) -> None:
        """
        Test that a difference reports members rather than plain integers.
        """

        statuses = dict(self.store.diff(1, 2))

        for status in statuses.values():
            self.assertIsInstance(status, RevisionStatus)

        self.assertEqual(
            statuses,
            {
                "a": RevisionStatus.ADDED,
                "b": RevisionStatus.CHANGED,
                "c": RevisionStatus.REMOVED,
            },
        )

    def test_diff_remains_comparable_to_integers(self) -> None:
        """
        Test that a difference still compares equal to the older integers.
        """

        self.assertEqual(dict(self.store.diff(1, 2)), {"a": 1, "b": 0, "c": -1})

    def test_members_are_cached(self) -> None:
        """
        Test that a difference yields the members themselves.

        The store holds the members in a tuple, so no member is constructed
        per yield. Identity therefore holds.
        """

        for status in dict(self.store.diff(1, 2)).values():
            self.assertIs(status, RevisionStatus(status))

    def test_swapping_inverts_the_status(self) -> None:
        """
        Test that swapping the revisions turns an addition into a removal.
        """

        forward = dict(self.store.diff(1, 2))
        backward = dict(self.store.diff(2, 1))

        self.assertEqual(forward["a"], RevisionStatus.ADDED)
        self.assertEqual(backward["a"], RevisionStatus.REMOVED)
        self.assertEqual(forward["b"], RevisionStatus.CHANGED)
        self.assertEqual(backward["b"], RevisionStatus.CHANGED)


if __name__ == "__main__":
    unittest.main()
