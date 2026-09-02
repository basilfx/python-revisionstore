"""
Mapping interfaces on top of a revisioned key-value store.

:class:`RevisionStore` speaks in terms of revisions, and iterates over values
rather than keys. The classes in this module wrap it in the mapping protocol,
so that a store can be used wherever a dictionary is expected.

These classes are deliberately plain Python. The traversal work is done by the
compiled store underneath.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any

from revisionstore.revisionstore import RevisionStatus, RevisionStore


class RevisionDictView(Mapping[Any, Any]):
    """
    Read-only mapping of the keys and values of a single revision.

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

    def __getitem__(self, key: Any) -> Any:
        """
        Return the value of a key in the revision of this view.

        :raises KeyError: If the key is unknown or removed in that revision.
        """

        return self._store.get(key, revision=self._revision)

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over the keys of this revision, in order of first insertion.
        """

        for key in self._store.lookup:
            if key in self:
                yield key

    def __len__(self) -> int:
        """
        Return the number of keys in this revision.

        Unlike the length of a store, this is linear in the number of keys
        that the store has ever held, because liveness is decided per key.
        """

        return sum(1 for _ in self)

    def __contains__(self, key: object) -> bool:
        """
        Check whether a key is present in the revision of this view.
        """

        try:
            self._store.get(key, revision=self._revision)
        except KeyError:
            return False

        return True

    def __repr__(self) -> str:
        """
        Return a representation of this view.
        """

        return f"{self.__class__.__name__}(revision={self._revision})"


class RevisionDict(MutableMapping[Any, Any]):
    """
    Mutable mapping that retains the value of every key per revision.

    The mapping protocol addresses the revision that is currently open, so the
    class behaves like a regular dictionary. The revision history is reached
    through :meth:`at`, and the store itself remains available as
    :attr:`store`.

    Note that assignment and deletion apply to the open revision. Calling
    :meth:`commit` closes it and opens the next one, which is what makes the
    preceding state readable afterwards.
    """

    __slots__ = ("_store",)

    _store: RevisionStore

    def __init__(self, store: RevisionStore | None = None) -> None:
        """
        Construct a mapping around a store.

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

    def __getitem__(self, key: Any) -> Any:
        """
        Return the value of a key in the current revision.

        :raises KeyError: If the key is unknown or removed.
        """

        return self._store.get(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        """
        Assign a value to a key in the current revision.
        """

        self._store.add(key, value)

    def __delitem__(self, key: Any) -> None:
        """
        Mark a key as removed in the current revision.

        :raises KeyError: If the key is unknown or already removed.
        """

        if key not in self._store:
            raise KeyError(key)

        self._store.remove(key)

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over the keys of the current revision.

        Keys are yielded in order of first insertion, as a dictionary does.
        Note that this differs from iterating the store itself, which yields
        values in the reverse order.
        """

        store: RevisionStore = self._store

        for key in store.lookup:
            if key in store:
                yield key

    def __len__(self) -> int:
        """
        Return the number of keys in the current revision.

        The store tracks the number of present keys, so this is constant time.
        """

        return len(self._store)

    def __contains__(self, key: object) -> bool:
        """
        Check whether a key is present in the current revision.
        """

        return key in self._store

    def at(self, revision: int = -1) -> RevisionDictView:
        """
        Return a read-only mapping of a given revision.

        :param revision: The revision to read, or `-1` for the current one.
        :return: A view on that revision.
        :raises ValueError: If the revision is out of bounds.
        """

        return RevisionDictView(self._store, revision)

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
        Discard the history of every key up to a given revision.

        :param revision: The revision to clean up to, or `-1` for the current
                         one.
        :raises ValueError: If the revision is out of bounds.
        """

        self._store.clean(revision)

    def diff(
        self, revision_a: int, revision_b: int
    ) -> Iterator[tuple[Any, RevisionStatus]]:
        """
        Compare two revisions and report the keys that differ.

        :param revision_a: The first revision to compare.
        :param revision_b: The second revision to compare.
        :return: A generator that yields tuples of a key and a status.
        :raises ValueError: If one of the revisions is out of bounds.
        """

        return self._store.diff(revision_a, revision_b)

    def __repr__(self) -> str:
        """
        Return a representation of this mapping.
        """

        return (
            f"{self.__class__.__name__}(revision={self._store.revision}, "
            f"keys={len(self)})"
        )
