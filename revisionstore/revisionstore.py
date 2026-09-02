"""
Implementation of a revisioned key-value store.

The store keeps every value that has ever been assigned to a key. Values are
grouped into revisions, and a revision is closed by committing it. Any closed
revision can be read back, so the store provides a complete history instead of
only the current state.

Internally, the entries form a doubly linked list in reverse insertion order.
Every node of that list additionally carries a chain of parent entries, which
holds the values that the key had in older revisions.

This module is written in the pure Python mode of Cython. The type annotations
are what the compiler turns into C types, so the module compiles to an
extension module while remaining importable as plain Python.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import IntEnum
from typing import Any

import cython


class RevisionStatus(IntEnum):
    """
    How a key differs between two revisions.

    A status is reported relative to the first of the two revisions that were
    compared, so swapping those arguments turns an addition into a removal.

    The class derives from :class:`enum.IntEnum`, so a member compares equal
    to the integer that :meth:`RevisionStore.diff` used to yield.
    """

    REMOVED = -1
    CHANGED = 0
    ADDED = 1


# The members are held in a tuple, indexed by the status plus one, so that
# resolving one compiles to a direct tuple index. The tuple is declared, which
# keeps it a C global rather than an entry in the module dictionary, and so
# saves a lookup per yield. Calling RevisionStatus(value) instead would cost
# roughly four times as much.
_STATUSES: tuple[RevisionStatus, ...] = cython.declare(
    tuple,
    (RevisionStatus.REMOVED, RevisionStatus.CHANGED, RevisionStatus.ADDED),
)


@cython.cfunc
def _status(value: cython.int) -> RevisionStatus:
    """
    Return the status that belongs to minus one, zero or one.

    :param value: The status as an integer.
    :return: The matching member of :class:`RevisionStatus`.
    """

    return _STATUSES[value + 1]


@cython.cclass
class RevisionStoreEntry:
    """
    Single value of a key, valid from a given revision onwards.

    An entry is immutable from the perspective of the user. Assigning a new
    value to a key creates a new entry that references the previous one as its
    parent.
    """

    value = cython.declare(object, visibility="readonly")
    revision = cython.declare(cython.int, visibility="readonly")
    removed = cython.declare(cython.bint, visibility="readonly")

    # These are declared as readonly so that the compiled extension exposes
    # them exactly as the pure Python module does. The type is given as a
    # string because the class is not yet bound while its own body executes.
    # Cython resolves that string, but its type stubs only accept a callable.
    previous: RevisionStoreEntry | None = cython.declare(
        "RevisionStoreEntry",  # type: ignore[call-overload]
        visibility="readonly",
    )
    next: RevisionStoreEntry | None = cython.declare(
        "RevisionStoreEntry",  # type: ignore[call-overload]
        visibility="readonly",
    )
    parent: RevisionStoreEntry | None = cython.declare(
        "RevisionStoreEntry",  # type: ignore[call-overload]
        visibility="readonly",
    )

    def __init__(
        self,
        value: object,
        revision: cython.int,
        removed: cython.bint = False,
    ) -> None:
        """
        Construct a new entry.

        :param value: The value to store, or `None` if the entry is a
                      tombstone.
        :param revision: The revision in which the entry was created.
        :param removed: Whether the entry marks the key as removed.
        """

        self.value = value
        self.revision = revision
        self.removed = removed

        # These are assigned by the store when the entry is linked in. They
        # are initialized explicitly so that the module also works when it is
        # imported as plain Python, where an annotation alone declares nothing.
        self.previous = None
        self.next = None
        self.parent = None

    def __repr__(self) -> str:
        """
        Return a representation of this entry.
        """

        return (
            f"{self.__class__.__name__}(revision={self.revision}, "
            f"removed={self.removed}, value={self.value})"
        )


@cython.cclass
class RevisionStore:
    """
    Key-value store that retains the value of every key per revision.

    The store starts at revision one. Values added with :meth:`add` and keys
    removed with :meth:`remove` belong to the revision that is currently open.
    Calling :meth:`commit` closes that revision and opens the next one, which
    makes the closed revision available for reading.
    """

    next: RevisionStoreEntry | None = cython.declare(
        RevisionStoreEntry, visibility="readonly"
    )

    lookup = cython.declare(dict[Any, RevisionStoreEntry], visibility="readonly")
    revision = cython.declare(cython.int, visibility="readonly")
    min_revision = cython.declare(cython.int, visibility="readonly")

    # Number of keys that are present and not removed in the current revision.
    # It is maintained incrementally so that __len__ stays constant time.
    _live = cython.declare(cython.int, visibility="readonly")

    def __init__(self) -> None:
        """
        Construct an empty store that is positioned at revision one.
        """

        self.next = None
        self.lookup = dict()
        self.revision = 1
        self.min_revision = 1
        self._live = 0

    @cython.cfunc
    def _add(
        self,
        key: object,
        value: RevisionStoreEntry,
        parent: RevisionStoreEntry | None = None,
    ) -> None:
        """
        Insert an entry into the linked list and the lookup table.

        If a parent entry is given, the new entry takes its place in the linked
        list and the parent entry is preserved as history. Otherwise, the new
        entry is prepended to the linked list.

        :param key: The key to insert the entry for.
        :param value: The entry to insert.
        :param parent: The entry that the new entry replaces, if any.
        """

        if parent is not None:
            value.parent = parent
            value.next = parent.next

            if value.next is not None:
                value.next.previous = value

            value.previous = parent.previous

            if value.previous is not None:
                value.previous.next = value
            else:
                self.next = value
        else:
            value.previous = None
            value.next = self.next
            self.next = value

            if value.next is not None:
                value.next.previous = value

        # For fast random lookup.
        self.lookup[key] = value

    @cython.cfunc
    def _check_revision(self, revision: cython.int) -> None:
        """
        Verify that a revision is within the bounds of this store.

        :param revision: The revision to verify.
        :raises ValueError: If the revision has been cleaned away or is not
                            reached yet.
        """

        if revision < self.min_revision:
            raise ValueError(
                f"Revision {revision} less than minimal revision {self.min_revision}."
            )

        if revision > self.revision:
            raise ValueError(
                f"Revision {revision} exceeds maximal revision {self.revision}."
            )

    def check_revision(self, revision: cython.int) -> None:
        """
        Verify that a revision is within the bounds of this store.

        :param revision: The revision to verify.
        :raises ValueError: If the revision has been cleaned away or is not
                            reached yet.
        """

        self._check_revision(revision)

    def __len__(self) -> int:
        """
        Return the number of keys in the current revision.

        Keys that are marked as removed are not counted. The number of present
        keys is tracked as keys are added and removed, so this is constant
        time.

        :return: The number of keys that are present.
        """

        return self._live

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over the values of the current revision.

        :return: A generator that yields every value that is not removed.
        """

        return self.iterate()

    def __bool__(self) -> bool:
        """
        Coerce this store to a boolean.

        :return: `True` if at least one key is present and not removed.
        """

        return self._live > 0

    def __contains__(self, key: object) -> bool:
        """
        Check whether a given key exists and is not marked as removed.

        :param key: The key to look for.
        :return: `True` if the key is present in the current revision.
        """

        current: RevisionStoreEntry | None = self.lookup.get(key)

        return current is not None and not current.removed

    def __repr__(self) -> str:
        """
        Return a representation of this store.
        """

        return (
            f"{self.__class__.__name__}(min_revision={self.min_revision}, "
            f"revision={self.revision})"
        )

    def iterate(self, revision: cython.int = -1) -> Iterator[Any]:
        """
        Iterate over the values of a given revision.

        Values are yielded in reverse order of first insertion, so the most
        recently added key comes first.

        :param revision: The revision to read, or `-1` for the current one.
        :return: A generator that yields every value that is not removed.
        :raises ValueError: If the revision is out of bounds.
        """

        current: RevisionStoreEntry | None = self.next

        # Optimize for no revision.
        if revision == -1:
            while current is not None:
                if not current.removed:
                    yield current.value

                current = current.next
        else:
            self._check_revision(revision)

            while current is not None:
                if revision < current.revision:
                    if current.parent is not None:
                        current = current.parent
                    else:
                        current = current.next
                else:
                    if not current.removed:
                        yield current.value

                    current = current.next

    def commit(self, revision: cython.int = -1) -> None:
        """
        Close the current revision and open the next one.

        :param revision: The revision to advance to, or `-1` to advance by one.
        :raises ValueError: If the given revision is not greater than the
                            current one.
        """

        if revision == -1:
            self.revision += 1
        else:
            if revision <= self.revision:
                raise ValueError(
                    f"Can only commit to a revision greater than "
                    f"{self.revision} ({revision} was given)."
                )

            self.revision = revision

    def get(self, key: object, revision: cython.int = -1) -> Any:
        """
        Look up the value of a key in a given revision.

        :param key: The key to look up.
        :param revision: The revision to read, or `-1` for the current one.
        :return: The value of the key in the given revision.
        :raises KeyError: If the key is unknown or removed in that revision.
        :raises ValueError: If the revision is out of bounds.
        """

        entry: RevisionStoreEntry = self.lookup[key]

        # Optimize for no revision.
        if revision == -1:
            if entry.removed:
                raise KeyError(f"Key '{key}' marked as removed.")

            return entry.value

        self._check_revision(revision)

        current: RevisionStoreEntry | None = entry

        while current is not None:
            if revision < current.revision:
                current = current.parent
            else:
                if current.removed:
                    raise KeyError(f"Key '{key}' marked as removed.")

                return current.value

        raise KeyError(f"Key '{key}' does not exist in revision {revision}.")

    def since(self, value: object) -> int:
        """
        Return the earliest revision that holds a value.

        Unlike :meth:`get`, this searches by value rather than by key, and the
        store holds no index of its values. Every entry is therefore visited,
        which makes the cost linear in the number of entries that the store
        has ever held. The search stops early once the oldest revision that
        the store still holds is reached, since nothing can predate it.

        A value is matched on equality, with identity as a shortcut, as a list
        does. Entries that mark a key as removed hold no value and are skipped,
        so a tombstone never matches.

        Only values that a revision can actually report are considered. An
        entry holds from its own revision until the next entry of its key
        replaces it, and revisions older than :attr:`min_revision` can no
        longer be read. A value whose entry holds outside that window alone is
        therefore not found. Assigning a key twice within one revision, for
        instance, hides the first of the two values, exactly as a difference
        disregards it.

        Note that the result is the earliest occurrence of the value. A value
        that was assigned, removed and assigned again reports the first of
        those revisions, even though it did not hold continuously since then.

        The result is never older than :attr:`min_revision`, so it can always
        be read back.

        :param value: The value to look for.
        :return: The earliest revision that holds the value.
        :raises ValueError: If no entry holds the value.
        """

        current: RevisionStoreEntry | None = self.next
        parent: RevisionStoreEntry | None

        # Revisions start at one, so zero marks that nothing matched yet.
        earliest: cython.int = 0
        start: cython.int
        stop: cython.int
        newer: cython.int
        minimum: cython.int = self.min_revision
        maximum: cython.int = self.revision

        # Walk the linked list of the newest entry of every key, and the chain
        # of parents that hangs off each of those. Together they are every
        # entry that the store holds. The key is never needed, so this is a
        # walk over typed pointers alone.
        while current is not None:
            parent = current

            # The revision of the entry that precedes the current one in the
            # chain, which is the newer of the two. Zero while there is none.
            newer = 0

            while parent is not None:
                # An entry holds from its own revision up to the one before
                # the entry that replaced it, or up to the open revision when
                # nothing replaced it. Cleaning cannot be read past, so the
                # window starts at the oldest readable revision at the latest.
                stop = maximum if newer == 0 else newer - 1
                start = parent.revision
                newer = parent.revision

                if start < minimum:
                    start = minimum

                # The bounds are integers, so they are tested before the value
                # itself is compared.
                if start <= stop and (earliest == 0 or start < earliest):
                    if not parent.removed and (
                        parent.value is value or parent.value == value
                    ):
                        earliest = start

                        if earliest == minimum:
                            return earliest

                parent = parent.parent

            current = current.next

        if earliest == 0:
            raise ValueError(f"Value {value!r} not held by any revision.")

        return earliest

    def remove(self, key: object) -> None:
        """
        Mark a key as removed in the current revision.

        The value of the key in older revisions is retained.

        :param key: The key to remove.
        :raises KeyError: If the key is unknown.
        """

        parent: RevisionStoreEntry = self.lookup[key]

        if not parent.removed:
            self._live -= 1

        # Wrap in a tombstone entry.
        entry: RevisionStoreEntry = RevisionStoreEntry(
            value=None, revision=self.revision, removed=True
        )

        # Replace in the linked list.
        self._add(key, entry, parent=parent)

    def clean(self, revision: cython.int = -1) -> None:
        """
        Discard the history of every key up to a given revision.

        After cleaning, revisions older than the given one can no longer be
        read.

        :param revision: The revision to clean up to, or `-1` for the current
                         one.
        :raises ValueError: If the revision is out of bounds.
        """

        current: RevisionStoreEntry | None = self.next
        previous: RevisionStoreEntry

        # Optimize for no revision.
        if revision == -1:
            while current is not None:
                current.parent = None
                current = current.next
        else:
            self._check_revision(revision)

            while current is not None:
                previous = current

                if revision < current.revision:
                    if current.parent is not None:
                        current = current.parent
                    else:
                        current = current.next
                else:
                    previous.parent = None
                    current = current.next

        # Store the new minimal revision.
        self.min_revision = revision if revision != -1 else self.revision

    def add(self, key: object, value: object) -> None:
        """
        Assign a value to a key in the current revision.

        The value that the key had in older revisions is retained.

        :param key: The key to assign to.
        :param value: The value to assign.
        """

        parent: RevisionStoreEntry | None = self.lookup.get(key)

        if parent is None or parent.removed:
            self._live += 1

        # Wrap in an entry.
        entry: RevisionStoreEntry = RevisionStoreEntry(
            value=value, revision=self.revision
        )

        # Add to (or replace in) the linked list.
        self._add(key, entry, parent=parent)

    def diff(
        self, revision_a: cython.int, revision_b: cython.int
    ) -> Iterator[tuple[Any, RevisionStatus]]:
        """
        Compare two revisions and report the keys that differ.

        For every differing key, a tuple of the key and a status is yielded.
        The status is :attr:`RevisionStatus.ADDED` if the key was added,
        :attr:`RevisionStatus.REMOVED` if the key was removed and
        :attr:`RevisionStatus.CHANGED` if the value of the key was changed. It
        is relative to the first revision, so swapping the arguments turns an
        addition into a removal.

        :param revision_a: The first revision to compare.
        :param revision_b: The second revision to compare.
        :return: A generator that yields tuples of a key and a status.
        :raises ValueError: If one of the revisions is out of bounds.
        """

        current: RevisionStoreEntry | None
        start: RevisionStoreEntry | None
        stop: RevisionStoreEntry | None
        direction: cython.int

        self._check_revision(revision_a)
        self._check_revision(revision_b)

        # Swap the direction if the first revision is the older one.
        if revision_a < revision_b:
            revision_a, revision_b = revision_b, revision_a
            direction = -1
        else:
            direction = 1

        # Iterate over all keys.
        for key in self.lookup:
            current = self.lookup[key]

            start = None
            stop = None

            # Find the start entry.
            while current is not None:
                if current.revision <= revision_a:
                    start = current
                    break

                current = current.parent

            if start is None or start.revision < revision_a:
                continue

            # Skip the entries of the same revision.
            while current is not None:
                if current.revision != start.revision:
                    break

                current = current.parent

            # Find the stop entry.
            while current is not None:
                if current.revision <= revision_b:
                    stop = current
                    break

                current = current.parent

            if stop is None:
                yield key, _status(direction)
                continue

            # Decide on the status.
            if revision_a == revision_b:
                if not start.removed:
                    yield key, _status(direction)
            else:
                if start.removed and not stop.removed:
                    yield key, _status(-1 * direction)
                elif not start.removed and stop.removed:
                    yield key, _status(direction)
                else:
                    yield key, _status(0)
