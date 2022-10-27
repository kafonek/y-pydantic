# y-pydantic
Ypy bindings to Pydantic models. See `notebooks/` for examples. Right now, this is purely a learning project and is not published to Pypi or anything. 


Think about the Y ecosystem as having three core concepts:

 - The Y CRDT and shared data types, implemented in yjs (JS) and yrs (Rust), ported to ypy (Python) via maturin
 - bindings that connect a CRDT with something you can see or interact with, such as a codemirror element in an HTML document
 - providers that synchronize different clients over wire protocols (webrtc, websockets, etc) using a small messaging protocol and then exchanging state vectors and diffs (aka deltas or updates).

`y-pydantic` deals with the second of those bullets, automatically updating Pydantic models when observing changes applied to different Y shared data types.