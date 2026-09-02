"""
Key-value store that retains the value of every key per revision.

This package exposes :class:`RevisionStore`, the revisioned store itself, and
:class:`RevisionDict`, :class:`RevisionList` and :class:`RevisionSet`, which
present a store through the mapping, sequence and set protocols.
"""

from revisionstore.revisiondict import RevisionDict, RevisionDictView
from revisionstore.revisionlist import RevisionList, RevisionListView
from revisionstore.revisionset import RevisionSet, RevisionSetView
from revisionstore.revisionstore import (
    RevisionStatus,
    RevisionStore,
    RevisionStoreEntry,
)

__all__ = [
    "RevisionDict",
    "RevisionDictView",
    "RevisionList",
    "RevisionListView",
    "RevisionSet",
    "RevisionSetView",
    "RevisionStatus",
    "RevisionStore",
    "RevisionStoreEntry",
]

__version__ = "1.0.0"
