# revisionstore

Key-value store that retains the value of every key per revision, implemented
in Cython.

`revisionstore` does not overwrite values. It keeps the value that every key
held in every revision, so that past revisions can be read back and compared.

The package offers several interfaces on the same data:

- `RevisionStore`, the store itself, which speaks in revisions and iterates
  over values.
- `RevisionDict`, which presents a store through the mapping protocol, so it
  can be used wherever a dictionary is expected.
- `RevisionList` and `RevisionSet`, which present a store through the sequence
  and set protocols.

This project has been extracted from [flask-daapserver], where it was used to
provide a revisioned in-memory database to stream music library deltas to
clients. It is now a standalone package.

## Installation

```bash
pip install revisionstore
```

A C compiler is required when no wheel is available for the current platform.

## Usage

### As a dictionary

`RevisionDict` is a `MutableMapping`. The mapping protocol addresses the
revision that is currently open, so it behaves like a regular dictionary.

```python
from revisionstore import RevisionDict

songs = RevisionDict()
songs["artist"] = "Bob Dylan"
songs["title"] = "Like a Rolling Stone"
songs.commit()  #  closes revision 1 and opens revision 2

songs["title"] = "Blowin' in the Wind"
songs.commit()  # closes revision 2 and opens revision 3

len(songs)  # 2
songs["title"]  # "Blowin' in the Wind"
dict(songs)  # {"artist": "Bob Dylan", "title": "Blowin' in the Wind"}
list(songs)  # ["artist", "title"]
songs.get("year", 1963)  # 1963
```

Assignment and deletion apply to the open revision. Calling `commit` closes it
and opens the next one, which is what makes the preceding state readable
afterwards.

Past revisions are reached with `at`, which returns a read-only `Mapping`:

```python
del songs["artist"]

dict(songs)  # {"title": "Blowin' in the Wind"}
dict(songs.at(1))  # {"artist": "Bob Dylan", "title": "Like a Rolling Stone"}
songs.at(2)["title"]  # "Blowin' in the Wind"
```

Two revisions are compared with `diff`. For every key that differs, a tuple of
the key and a `RevisionStatus` is yielded. The status is relative to the first
revision, so swapping the arguments turns an addition into a removal.

```python
list(songs.diff(2, 1))  # [("title", <RevisionStatus.CHANGED: 0>)]
list(songs.diff(3, 2))  # [("artist", <RevisionStatus.REMOVED: -1>)]
list(songs.diff(2, 3))  # [("artist", <RevisionStatus.ADDED: 1>)]
```

History costs memory. Once older revisions are no longer of interest, `clean`
discards them. Reading a revision below `min_revision` raises a `ValueError`
afterwards.

```python
songs.clean(revision=2)
songs.min_revision  # 2
songs.at(1)  # raises ValueError
```

### As a list

`RevisionList` presents a store through the sequence protocol. The position is
used as the key, so every position keeps its own history.

```python
from revisionstore import RevisionList

tracks = RevisionList()
tracks.append("Like a Rolling Stone")
tracks.append("Blowin' in the Wind")
tracks.commit()

tracks[0] = "Mr. Tambourine Man"
tracks.commit()

list(tracks)  # ["Mr. Tambourine Man", "Blowin' in the Wind"]
list(tracks.at(1))  # ["Like a Rolling Stone", "Blowin' in the Wind"]
```

Because the position is the key, inserting or deleting anywhere but at the end
renumbers every position that follows, and each of those is written again in
the open revision. Such an operation therefore costs a new entry per element,
and reports every renumbered position as changed:

```python
del tracks[0]
tracks.commit()

# Position 0 holds a different value, and position 1 exists in revision two
# only, because the sequence became shorter.
dict(tracks.diff(2, 3))
# {0: <RevisionStatus.CHANGED: 0>, 1: <RevisionStatus.ADDED: 1>}
```

### As a set

`RevisionSet` presents a store through the set protocol. Every element is
stored as its own value, so the store holds only the elements.

```python
from revisionstore import RevisionSet

genres = RevisionSet()
genres.add("folk")
genres.add("rock")
genres.commit()

genres.discard("rock")
genres.commit()

set(genres)  # {"folk"}
set(genres.at(1))  # {"folk", "rock"}
```

Adding an element that is already present does nothing, so that the history of
that element is not extended without a change. The operators of the protocol,
such as `|` and `&`, return a plain set rather than a revisioned one.

### As a store

`RevisionStore` is the underlying primitive. It takes an explicit revision on
every read, and iterating it yields **values** in reverse order of first
insertion, which is what makes it convenient for serving incremental updates.

```python
from revisionstore import RevisionStore

store = RevisionStore()
store.add("artist", "Bob Dylan")
store.add("title", "Like a Rolling Stone")
store.commit()

store.add("title", "Blowin' in the Wind")

store.get("title")  # "Blowin' in the Wind"
store.get("title", revision=1)  # "Like a Rolling Stone"
list(store.iterate())  # ["Blowin' in the Wind", "Bob Dylan"]
list(store.iterate(revision=1))  # ["Like a Rolling Stone", "Bob Dylan"]
```

Where `get` searches by key, `since` searches by value, and reports the
earliest revision that holds it. The store keeps no index of its values, so
this walks every entry.

```python
store.since("Bob Dylan")  # 1
store.since("Blowin' in the Wind")  # 2
```

Only values that a revision can report are found. A value that was replaced
within a single revision, or that a `clean` has made unreadable, raises a
`ValueError`, as does a value the store never held.

A mapping can be wrapped around an existing store, and both interfaces then
address the same data:

```python
songs = RevisionDict(store)
songs["year"] = 1963

store.get("year")  # 1963
songs.store is store  # True
```

Take care not to mix the two interfaces carelessly. `RevisionStore` iterates
values while `RevisionDict` iterates keys, and `RevisionStore.get` raises a
`KeyError` for a missing key where `RevisionDict.get` returns a default.

## Implementation

The store is written in the [pure Python mode][pure] of Cython. There is a
single implementation file, `revisionstore/revisionstore.py`, which is ordinary
Python annotated with `cython` types:

```python
@cython.cclass
class RevisionStoreEntry:
    revision = cython.declare(cython.int, visibility="readonly")

    previous: RevisionStoreEntry | None
    next: RevisionStoreEntry | None
    parent: RevisionStoreEntry | None
```

Those annotations are what the compiler turns into C types, so this compiles to
the same C code that a `.pyx` plus `.pxd` pair would produce. The classes
become C extension types with C struct fields, and the private methods become C
functions dispatched through a vtable.

Because the module is also valid Python, it runs without being compiled, at
roughly a third of the speed. The compiled extension shadows the `.py` at
import time, so the module never needs `cython` at run time. Use
`cython.compiled` to tell the two apart.

The modules that provide the mapping, sequence and set interfaces,
`revisionstore/revisiondict.py`, `revisionstore/revisionlist.py` and
`revisionstore/revisionset.py`, are deliberately not compiled. They are thin
layers, and the traversal work happens in the store underneath.

Note that type checkers read the `.py` and therefore have to resolve
`import cython`. A project that type checks its use of this package needs
`cython` installed as well, otherwise the annotations silently degrade to
`Any`.

[pure]: https://cython.readthedocs.io/en/latest/src/tutorial/pure.html

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management,
and builds the Cython extension through `setuptools`.

```bash
uv sync               # create the environment and build the extension
uv run pytest         # run the tests
uv run ruff check .   # lint
uv run ruff format .  # format
uv run mypy           # type check
```

The extension is rebuilt automatically when `revisionstore/revisionstore.py`
changes and `uv sync` or `uv run` is invoked.

## License

See the [LICENSE.md](LICENSE.md) file (MIT license).

[flask-daapserver]: https://github.com/basilfx/flask-daapserver