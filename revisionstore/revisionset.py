"""
Set interfaces on top of a revisioned key-value store.

:class:`RevisionStore` maps a key to a value, whereas a set carries elements
alone. The classes in this module store every element as its own value, so
that a store can be used wherever a set is expected.

These classes are deliberately plain Python. The traversal work is done by the
compiled store underneath.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, MutableSet, Set
from typing import Any

from revisionstore.revisionstore import RevisionStatus, RevisionStore


class RevisionSetView(Set[Any]):
    """
    Read-only set of the elements of a single revision.

    A view is a window on a live store, not a copy. Committing to the store
    does not affect the view, but cleaning the store past the revision of the
    view invalidates it.
    """

    __slots__ = ("_revision", "_store")

    _store: RevisionStore
    _revision: int

    def __init__(self, store: RevisionStore, revision: int = -1) -> None:
        """
        Construct a view on a revision of a store.

        :param store: The store to read from.
        :param revision: The revision to read, or `-1` for the current one.
        :raises ValueError: If the revision is out of bounds.
        """

        if revision == -1:
            revision = store.revision

        store.check_revision(revision)

        self._store = store
        self._revision = revision

    @classmethod
    def _from_iterable(cls, iterable: Iterable[Any]) -> set[Any]:
        """
        Build a plain set from an iterable.

        The operators of the set protocol construct their result by calling
        this method. A view cannot be built from elements alone, because it is
        bound to a store and a revision, so a plain set is returned instead.

        :param iterable: The elements of the result.
        :return: A plain set of those elements.
        """

        return set(iterable)

    @property
    def revision(self) -> int:
        """
        Return the revision that this view reads.
        """

        return self._revision

    @property
    def store(self) -> RevisionStore:
        """
        Return the underlying store.
        """

        return self._store

    def __contains__(self, element: object) -> bool:
        """
        Check whether an element is present in the revision of this view.
        """

        try:
            self._store.get(element, revision=self._revision)
        except KeyError:
            return False

        return True

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over the elements of this revision, in order of first
        insertion.
        """

        for element in self._store.lookup:
            if element in self:
                yield element

    def __len__(self) -> int:
        """
        Return the number of elements in this revision.

        Unlike the length of a set, this is linear in the number of elements
        that the store has ever held, because presence is decided per element.
        """

        return sum(1 for _ in self)

    def __repr__(self) -> str:
        """
        Return a representation of this view.
        """

        return f"{self.__class__.__name__}(revision={self._revision})"


class RevisionSet(MutableSet[Any]):
    """
    Mutable set that retains the presence of every element per revision.

    The set protocol addresses the revision that is currently open, so the
    class behaves like a regular set. The revision history is reached through
    :meth:`at`, and the store itself remains available as :attr:`store`.

    Note that addition and discarding apply to the open revision. Calling
    :meth:`commit` closes it and opens the next one, which is what makes the
    preceding state readable afterwards.
    """

    __slots__ = ("_store",)

    _store: RevisionStore

    def __init__(self, store: RevisionStore | None = None) -> None:
        """
        Construct a set around a store.

        :param store: The store to wrap, or `None` to create an empty one.
        """

        self._store = RevisionStore() if store is None else store

    @classmethod
    def _from_iterable(cls, iterable: Iterable[Any]) -> set[Any]:
        """
        Build a plain set from an iterable.

        The operators of the set protocol construct their result by calling
        this method. A revisioned set cannot be built from elements alone,
        because it is bound to a store, so a plain set is returned instead.

        :param iterable: The elements of the result.
        :return: A plain set of those elements.
        """

        return set(iterable)

    @property
    def store(self) -> RevisionStore:
        """
        Return the underlying store.
        """

        return self._store

    @property
    def revision(self) -> int:
        """
        Return the revision that is currently open.
        """

        return self._store.revision

    @property
    def min_revision(self) -> int:
        """
        Return the oldest revision that can still be read.
        """

        return self._store.min_revision

    def add(self, value: Any) -> None:
        """
        Add an element to the current revision.

        Adding an element that is already present does nothing, so that the
        history of that element is not extended without a change.
        """

        if value not in self._store:
            self._store.add(value, value)

    def discard(self, value: Any) -> None:
        """
        Mark an element as removed in the current revision.

        Discarding an element that is absent does nothing.
        """

        if value in self._store:
            self._store.remove(value)

    def __contains__(self, element: object) -> bool:
        """
        Check whether an element is present in the current revision.
        """

        return element in self._store

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over the elements of the current revision.

        Elements are yielded in order of first insertion. Note that this
        differs from iterating the store itself, which yields values in the
        reverse order.
        """

        store: RevisionStore = self._store

        for element in store.lookup:
            if element in store:
                yield element

    def __len__(self) -> int:
        """
        Return the number of elements in the current revision.

        The store tracks the number of present elements, so this is constant
        time.
        """

        return len(self._store)

    def at(self, revision: int = -1) -> RevisionSetView:
        """
        Return a read-only set of a given revision.

        :param revision: The revision to read, or `-1` for the current one.
        :return: A view on that revision.
        :raises ValueError: If the revision is out of bounds.
        """

        return RevisionSetView(self._store, revision)

    def commit(self, revision: int = -1) -> None:
        """
        Close the current revision and open the next one.

        :param revision: The revision to advance to, or `-1` to advance by one.
        :raises ValueError: If the given revision is not greater than the
                            current one.
        """

        self._store.commit(revision)

    def clean(self, revision: int = -1) -> None:
        """
        Discard the history of every element up to a given revision.

        :param revision: The revision to clean up to, or `-1` for the current
                         one.
        :raises ValueError: If the revision is out of bounds.
        """

        self._store.clean(revision)

    def diff(
        self, revision_a: int, revision_b: int
    ) -> Iterator[tuple[Any, RevisionStatus]]:
        """
        Compare two revisions and report the elements that differ.

        :param revision_a: The first revision to compare.
        :param revision_b: The second revision to compare.
        :return: A generator that yields tuples of an element and a status.
        :raises ValueError: If one of the revisions is out of bounds.
        """

        return self._store.diff(revision_a, revision_b)

    def __repr__(self) -> str:
        """
        Return a representation of this set.
        """

        return (
            f"{self.__class__.__name__}(revision={self._store.revision}, "
            f"elements={len(self)})"
        )
