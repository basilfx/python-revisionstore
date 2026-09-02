"""
Sequence interfaces on top of a revisioned key-value store.

:class:`RevisionStore` maps a key to a value, whereas a sequence addresses its
values by position. The classes in this module use the position as the key, so
that a store can be used wherever a list is expected.

Because the position is the key, inserting or deleting anywhere but at the end
renumbers every element that follows. Each of those elements is written again
in the open revision, so such an operation costs a new entry per element and
reports every renumbered position as changed in a difference.

These classes are deliberately plain Python. The traversal work is done by the
compiled store underneath.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableSequence, Sequence
from typing import Any

from revisionstore.revisionstore import RevisionStatus, RevisionStore


class RevisionListView(Sequence[Any]):
    """
    Read-only sequence of the values of a single revision.

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

    def __getitem__(self, index: Any) -> Any:
        """
        Return the value at a position in the revision of this view.

        :raises IndexError: If the position is out of range.
        """

        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]

        if index < 0:
            index += len(self)

            if index < 0:
                raise IndexError("list index out of range")

        try:
            return self._store.get(index, revision=self._revision)
        except KeyError:
            raise IndexError("list index out of range") from None

    def __len__(self) -> int:
        """
        Return the number of values in this revision.

        Unlike the length of a list, this is linear in the number of positions
        that the store has ever held, because presence is decided per
        position.
        """

        store: RevisionStore = self._store
        revision: int = self._revision
        length: int = 0

        for position in store.lookup:
            try:
                store.get(position, revision=revision)
            except KeyError:
                continue

            length += 1

        return length

    def __repr__(self) -> str:
        """
        Return a representation of this view.
        """

        return f"{self.__class__.__name__}(revision={self._revision})"


class RevisionList(MutableSequence[Any]):
    """
    Mutable sequence that retains the value of every position per revision.

    The sequence protocol addresses the revision that is currently open, so
    the class behaves like a regular list. The revision history is reached
    through :meth:`at`, and the store itself remains available as
    :attr:`store`.

    Note that assignment, insertion and deletion apply to the open revision.
    Calling :meth:`commit` closes it and opens the next one, which is what
    makes the preceding state readable afterwards.
    """

    __slots__ = ("_store",)

    _store: RevisionStore

    def __init__(self, store: RevisionStore | None = None) -> None:
        """
        Construct a sequence around a store.

        :param store: The store to wrap, or `None` to create an empty one.
        """

        self._store = RevisionStore() if store is None else store

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

    def _resolve(self, index: int) -> int:
        """
        Turn a position into an index that the store holds.

        :param index: The position to resolve, which may be negative.
        :return: The resolved position.
        :raises IndexError: If the position is out of range.
        """

        if index < 0:
            index += len(self)

        if index < 0 or index not in self._store:
            raise IndexError("list index out of range")

        return index

    def _rewrite(self, values: list[Any]) -> None:
        """
        Replace the whole sequence with the given values.

        Positions that fall beyond the new length are marked as removed.

        :param values: The values that the sequence must hold.
        """

        store: RevisionStore = self._store
        length: int = len(self)

        for position, value in enumerate(values):
            store.add(position, value)

        for position in range(len(values), length):
            store.remove(position)

    def __getitem__(self, index: Any) -> Any:
        """
        Return the value at a position in the current revision.

        :raises IndexError: If the position is out of range.
        """

        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]

        if index < 0:
            index += len(self)

            if index < 0:
                raise IndexError("list index out of range")

        try:
            return self._store.get(index)
        except KeyError:
            raise IndexError("list index out of range") from None

    def __setitem__(self, index: Any, value: Any) -> None:
        """
        Assign a value to a position in the current revision.

        Assigning to a single position costs one entry. A slice is assigned by
        rewriting the sequence, which writes every position again.

        :raises IndexError: If the position is out of range.
        """

        if isinstance(index, slice):
            values: list[Any] = list(self)
            values[index] = value

            self._rewrite(values)

            return

        self._store.add(self._resolve(index), value)

    def __delitem__(self, index: Any) -> None:
        """
        Remove the value at a position in the current revision.

        Every position that follows is renumbered, which writes each of those
        positions again and reports each of them as changed in a difference.
        Removing the last position, as :meth:`pop` does, costs one entry.

        :raises IndexError: If the position is out of range.
        """

        if isinstance(index, slice):
            values = list(self)

            del values[index]

            self._rewrite(values)

            return

        index = self._resolve(index)

        store: RevisionStore = self._store
        length: int = len(self)

        for position in range(index, length - 1):
            store.add(position, store.get(position + 1))

        store.remove(length - 1)

    def insert(self, index: int, value: Any) -> None:
        """
        Insert a value at a position in the current revision.

        Every position that follows is renumbered, which writes each of those
        positions again and reports each of them as changed in a difference.
        Inserting at the end, as :meth:`append` does, costs one entry. As with
        a list, a position out of range is clamped instead of rejected.

        :param index: The position to insert at.
        :param value: The value to insert.
        """

        store: RevisionStore = self._store
        length: int = len(self)

        if index < 0:
            index = max(0, index + length)
        else:
            index = min(index, length)

        for position in range(length, index, -1):
            store.add(position, store.get(position - 1))

        store.add(index, value)

    def __len__(self) -> int:
        """
        Return the number of values in the current revision.

        The store tracks the number of present positions, so this is constant
        time.
        """

        return len(self._store)

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over the values of the current revision, in order.
        """

        store: RevisionStore = self._store

        for position in range(len(self)):
            yield store.get(position)

    def at(self, revision: int = -1) -> RevisionListView:
        """
        Return a read-only sequence of a given revision.

        :param revision: The revision to read, or `-1` for the current one.
        :return: A view on that revision.
        :raises ValueError: If the revision is out of bounds.
        """

        return RevisionListView(self._store, revision)

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
        Discard the history of every position up to a given revision.

        :param revision: The revision to clean up to, or `-1` for the current
                         one.
        :raises ValueError: If the revision is out of bounds.
        """

        self._store.clean(revision)

    def diff(
        self, revision_a: int, revision_b: int
    ) -> Iterator[tuple[Any, RevisionStatus]]:
        """
        Compare two revisions and report the positions that differ.

        :param revision_a: The first revision to compare.
        :param revision_b: The second revision to compare.
        :return: A generator that yields tuples of a position and a status.
        :raises ValueError: If one of the revisions is out of bounds.
        """

        return self._store.diff(revision_a, revision_b)

    def __repr__(self) -> str:
        """
        Return a representation of this sequence.
        """

        return (
            f"{self.__class__.__name__}(revision={self._store.revision}, "
            f"values={len(self)})"
        )
