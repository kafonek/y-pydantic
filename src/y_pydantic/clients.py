from typing import List

import y_py as Y


class SyncClient:
    def __init__(self, pool: "ClientPool"):
        self.doc: Y.YDoc = Y.YDoc()
        self.pool = pool
        self.doc.observe_after_transaction(self.sync)

    def sync(self, event: Y.AfterTransactionEvent):
        diff = event.get_update()
        if diff != b"\x00\x00":
            self.pool.sync(diff)


class ClientPool:
    def __init__(self, client_cls=SyncClient):
        self.clients: List[client_cls] = []
        self.client_cls = client_cls

    def create_client(self):
        client = self.client_cls(pool=self)
        self.clients.append(client)
        # In over-the-wire yjs protocol, the three steps below would be described as:
        # - send "sync step 1" with your state vector
        # - peer sends "sync step 2" with a diff you should apply
        # - you apply the diff and you're synced
        if self.clients:
            new_client_state: bytes = client.doc.begin_transaction().state_vector_v1()
            stateful_ydoc: Y.YDoc = self.clients[0].doc
            diff: bytes = stateful_ydoc.begin_transaction().diff_v1(new_client_state)
            client.doc.begin_transaction().apply_v1(diff)
        self.clients.append(client)
        return client

    def sync(self, diff: bytes):
        # Thanks to idempotency in Y algorithm, we don't need to worry about applying
        # the same diff multiple times.
        for client in self.clients:
            client.doc.begin_transaction().apply_v1(diff)
