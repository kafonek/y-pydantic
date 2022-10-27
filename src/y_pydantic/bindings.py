from dataclasses import Field
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple, Union

import y_py as Y
from pydantic import BaseModel, Field


#
# Models representing Y.Event deltas, which will be observed when we make changes
# to a Y.YDoc and attached types, or when we sync with another client and apply
# changes to our Y.YDoc / attached types via that sync.
#
class Delta(BaseModel):
    """
    Individual Deltas included in Y.Event.deltas lists
    """

    insert: Optional[Any] = None
    retain: Optional[int] = None
    delete: Optional[int] = None
    attributes: Optional[dict] = Field(default_factory=dict)


class Event(BaseModel):
    deltas: List[Delta]


Y_PYDANTIC_JSON_ENCODERS = {
    "TextBinding": lambda v: v.model.dict(),
    "ArrayBinding": lambda v: v.model.dict(),
    "MapBinding": lambda v: v.model.dict(),
}

#
# Model and Binding to a Y.YText object
#
class TextItem(BaseModel):
    """
    An individual item in the Y.YText object. Most of the time this is a single
    character, but Y.YText supports inserting arbitrary objects (list/dict).
    """

    value: Any
    attributes: Optional[dict] = Field(default_factory=dict)


class TextModel(BaseModel):
    items: List[TextItem] = Field(default_factory=list)
    deleted: List[TextItem] = Field(default_factory=list)

    @property
    def plain_text(self) -> str:
        return "".join(item.value for item in self.items if isinstance(item.value, str))

    def apply_event(self, event: Event):
        """
        Update the TextModel after observing a YTextEvent.
        """
        idx = 0
        for delta in event.deltas:
            if delta.insert:
                # Make copies of the attributes dict below otherwise each inserted item
                # will have the same reference and future updates will update all items
                if isinstance(delta.insert, str):
                    for c in delta.insert:
                        item = TextItem(value=c, attributes=delta.attributes.copy())
                        try:
                            self.items.insert(idx, item)
                        except IndexError:
                            self.items.append(item)
                        idx += 1

                else:
                    item = TextItem(
                        value=delta.insert, attributes=delta.attributes.copy()
                    )
                    try:
                        self.items.insert(idx, item)
                    except IndexError:
                        self.items.append(item)
                    idx += 1

            elif delta.retain:
                for _ in range(delta.retain):
                    self.items[idx].attributes.update(delta.attributes)
                    idx += 1

            elif delta.delete:
                for _ in range(delta.delete):
                    item = self.items.pop(idx)
                    self.deleted.append(item)


class TextBinding:
    """
    Model a YText object in Pydantic, and apply updates to that model whenever the YText
    CRDT changes, either through calling methods on this class or syncing the parent YDoc
    with other documents.
    """

    def __init__(self, parent_doc: Y.YDoc, ytext: Y.YText):
        self.doc = parent_doc
        self.ytext = ytext
        self.ytext.observe(self.obs)
        self.model = TextModel()
        self.events: List[Event] = []

    def obs(self, event: Y.YTextEvent):
        ev = Event(deltas=event.delta)
        self.events.append(ev)
        self.model.apply_event(ev)

    @property
    def plain_text(self) -> str:
        return self.model.plain_text

    # Cover all the same methods in YText object, with the convenience of automatically
    # entering into the parent doc transaction to apply them.
    def insert(self, index: int, chunk: str, attributes: Optional[dict] = None):
        with self.doc.begin_transaction() as txn:
            self.ytext.insert(txn, index=index, chunk=chunk, attributes=attributes)

    def insert_embed(self, index: int, embed: Any, attributes: Optional[dict] = None):
        with self.doc.begin_transaction() as txn:
            self.ytext.insert_embed(
                txn, index=index, embed=embed, attributes=attributes
            )

    def extend(self, chunk: str):
        with self.doc.begin_transaction() as txn:
            self.ytext.extend(txn, chunk=chunk)

    def format(self, index: int, length: int, attributes: Optional[dict] = None):
        with self.doc.begin_transaction() as txn:
            self.ytext.format(txn, index=index, length=length, attributes=attributes)

    def delete(self, index: int):
        with self.doc.begin_transaction() as txn:
            self.ytext.delete(txn, index=index)

    def delete_range(self, index: int, length: int):
        with self.doc.begin_transaction() as txn:
            self.ytext.delete_range(txn, index=index, length=length)

    def __repr__(self):
        return f"<TextBinding {self.plain_text}>"


#
# Model and Binding to a Y.YArray object
#
class ArrayModel(BaseModel):
    items: List[Any] = Field(default_factory=list)
    deleted: List[Any] = Field(default_factory=list)

    class Config:
        json_encoders = Y_PYDANTIC_JSON_ENCODERS


class ArrayBinding:
    def __init__(self, parent_doc: Y.YDoc, yarray: Y.YArray):
        self.doc = parent_doc
        self.yarray = yarray
        self.yarray.observe(self.obs)
        self.model = ArrayModel()
        self.events: List[Event]

    def obs(self, event: Y.YArrayEvent):
        ev = Event(deltas=event.delta)
        idx = 0
        for delta in ev.deltas:
            if delta.insert:
                for item in delta.insert:
                    # Cast YText / YArray / YMap to bindings
                    if isinstance(item, Y.YText):
                        item = TextBinding(parent_doc=self.doc, ytext=item)
                    elif isinstance(item, Y.YArray):
                        item = ArrayBinding(parent_doc=self.doc, yarray=item)
                    elif isinstance(item, Y.YMap):
                        item = MapBinding(parent_doc=self.doc, ymap=item)
                    try:
                        self.model.items.insert(idx, item)
                    except IndexError:
                        self.model.items.append(item)
                    idx += 1
            elif delta.retain:
                idx += delta.retain
            elif delta.delete:
                for _ in range(delta.delete):
                    self.model.deleted.append(self.model.items.pop(idx))

    # Cover all the same methods in YArray object, with the convenience of automatically
    # entering into the parent doc transaction to apply them.
    def insert(self, index: int, item: Any):
        with self.doc.begin_transaction() as txn:
            self.yarray.insert(txn, index=index, item=item)

    def insert_range(self, index: int, items: Iterable):
        with self.doc.begin_transaction() as txn:
            self.yarray.insert_range(txn, index=index, items=items)

    def append(self, item: Any):
        with self.doc.begin_transaction() as txn:
            self.yarray.append(txn, item=item)

    def extend(self, items: Iterable):
        with self.doc.begin_transaction() as txn:
            self.yarray.extend(txn, items=items)

    def delete(self, index: int):
        with self.doc.begin_transaction() as txn:
            self.yarray.delete(txn, index=index)

    def delete_range(self, index: int, length: int):
        with self.doc.begin_transaction() as txn:
            self.yarray.delete_range(txn, index=index, length=length)

    def __repr__(self):
        return f"<ArrayBinding {len(self.model.items)}>"


#
# Model and Binding to a Y.YMap object
#
class KeyChange(BaseModel):
    action: Literal["add", "update", "delete"]
    oldValue: Optional[Any] = None
    newValue: Optional[Any] = None


class MapEvent(BaseModel):
    keys: Dict[str, KeyChange]


class MapModel(BaseModel):
    items: Dict[str, Any] = Field(default_factory=dict)
    deleted: Dict[str, Any] = Field(default_factory=dict)


class MapBinding:
    def __init__(self, parent_doc: Y.YDoc, ymap: Y.YMap):
        self.doc = parent_doc
        self.ymap = ymap
        self.ymap.observe(self.obs)
        self.model = MapModel()
        self.events: List[Event]

    def obs(self, event: Y.YMapEvent):
        ev = MapEvent(keys=event.keys)
        for key, change in ev.keys.items():
            if change.action == "delete":
                self.model.deleted[key] = self.model.items.pop(key)
            else:
                # Cast YText / YArray / YMap to bindings
                if isinstance(change.newValue, Y.YText):
                    change.newValue = TextBinding(
                        parent_doc=self.doc, ytext=change.newValue
                    )
                elif isinstance(change.newValue, Y.YArray):
                    change.newValue = ArrayBinding(
                        parent_doc=self.doc, yarray=change.newValue
                    )
                elif isinstance(change.newValue, Y.YMap):
                    change.newValue = MapBinding(
                        parent_doc=self.doc, ymap=change.newValue
                    )
                if change.action == "add":
                    self.model.items[key] = change.newValue
                elif change.action == "update":
                    self.model.items[key] = change.newValue

    # Cover all the same methods in YMap object, with the convenience of automatically
    # entering into the parent doc transaction to apply them.
    def set(self, key: str, value: Any):
        with self.doc.begin_transaction() as txn:
            self.ymap.set(txn, key=key, value=value)

    def update(self, items: Union[Iterable[Tuple[str, Any]], Dict[str, Any]]):
        with self.doc.begin_transaction() as txn:
            self.ymap.update(txn, items=items)

    def pop(self, key: str, fallback: Optional[Any] = None) -> Any:
        with self.doc.begin_transaction() as txn:
            return self.ymap.pop(txn, key=key, fallback=fallback)

    def __repr__(self):
        return f"<MapBinding {len(self.model.items)}>"
