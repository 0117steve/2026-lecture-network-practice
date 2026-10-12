#!/usr/bin/env python3
"""Week 4 · Task 1 — Build reliable delivery on top of an unreliable channel.

Textbook §3.4 (reliable data transfer) and §3.5 (TCP's sequence numbers).

`UnreliableChannel` below loses packets, reorders them, duplicates them, and
delays them. It is the network as §3.4 models it. Your job is to move a file
across it and have the bytes arrive intact and in order.

That is the whole of TCP's reliability story with the congestion control taken
out, and it is worth building once by hand before you ever trust a socket again.

    python3 task1_rdt.py --verify
"""
import argparse, hashlib, random

PAYLOAD = 8            # bytes per packet - small, so you see the sequencing


class UnreliableChannel:
    """Loses 10%, duplicates 3%, reorders, and delays. Deterministic by seed.

    You may not make it nicer. You may not read its internals. It is the only
    way your sender can reach your receiver.
    """

    def __init__(self, seed=246, loss=0.10, dup=0.03, reorder=0.10):
        self.rng = random.Random(seed)
        self.loss, self.dup, self.reorder = loss, dup, reorder
        self.wire = []          # packets in flight, in no particular order
        self.stats = {"sent": 0, "lost": 0, "duplicated": 0, "delivered": 0}

    def send(self, packet):
        """Hand a packet to the network. It may never come out."""
        self.stats["sent"] += 1
        if self.rng.random() < self.loss:
            self.stats["lost"] += 1
            return
        copies = 2 if self.rng.random() < self.dup else 1
        self.stats["duplicated"] += copies - 1
        for _ in range(copies):
            if self.rng.random() < self.reorder and self.wire:
                self.wire.insert(self.rng.randrange(len(self.wire)), packet)
            else:
                self.wire.append(packet)

    def receive(self):
        """Take the next packet out, or None if the network has nothing."""
        if not self.wire:
            return None
        self.stats["delivered"] += 1
        return self.wire.pop(0)


class Sender:
    """Your sender.

    Requirements are in task1.md. The short version:

      - break `data` into PAYLOAD-sized pieces and number them
      - retransmit what is not acknowledged
      - do not assume an ACK means what you think it means until you have
        checked the number on it

    You choose the protocol: stop-and-wait is the easiest to get right and the
    slowest; a sliding window is the point of §3.4.3. Say which you chose and
    why in observation.md.
    """

    # Selective Repeat (sliding window, §3.4.4) with a cumulative field.
    #   packet on the wire : ("DATA", seq, payload)    seq = piece number
    #   ACK on the wire    : ("ACK", seq, cumulative)  "I have seq, and every
    #                                                   piece below cumulative"
    WINDOW = 8        # pieces allowed to be unacknowledged at once
    TIMEOUT = 10      # steps to wait for an ACK before sending a piece again

    def __init__(self, data_channel, ack_channel, data):
        self.data_channel = data_channel
        self.ack_channel = ack_channel
        # R1: cut into PAYLOAD-sized pieces; the list index is the sequence number
        self.pieces = [data[i:i + PAYLOAD] for i in range(0, len(data), PAYLOAD)]
        self.base = 0             # oldest piece not yet acknowledged
        self.next_seq = 0         # next piece never sent before
        self.acked = set()
        self.sent_at = {}         # seq -> step it was last (re)transmitted
        self.clock = 0

    def step(self):
        """Do one unit of work. Return False when you believe you are done."""
        self.clock += 1

        # 1. Read every ACK that has arrived. Check the number on each one:
        #    a duplicated or very late ACK names a piece we already counted,
        #    and anything outside what we have sent is ignored.
        while True:
            ack = self.ack_channel.receive()
            if ack is None:
                break
            kind, seq, cumulative = ack
            if kind != "ACK":
                continue
            # The ACK names one piece *and* says "everything below `cumulative`
            # has arrived". The second half means a lost ACK costs nothing as
            # long as any later ACK gets through.
            for s in [seq, *range(self.base, min(cumulative, self.next_seq))]:
                if self.base <= s < self.next_seq and s not in self.acked:
                    self.acked.add(s)
                    self.sent_at.pop(s, None)
        while self.base in self.acked:            # slide the window forward
            self.acked.discard(self.base)
            self.base += 1

        if self.base >= len(self.pieces):
            return False                          # every piece acknowledged

        # 2. Send at most one packet per step.
        #    R4: the oldest piece whose timer ran out goes first...
        for seq in sorted(self.sent_at):
            if self.clock - self.sent_at[seq] >= self.TIMEOUT:
                self._transmit(seq)
                return True
        #    ...otherwise a new piece, if the window has room.
        if self.next_seq < len(self.pieces) and self.next_seq < self.base + self.WINDOW:
            self._transmit(self.next_seq)
            self.next_seq += 1
        return True

    def _transmit(self, seq):
        self.data_channel.send(("DATA", seq, self.pieces[seq]))
        self.sent_at[seq] = self.clock


class Receiver:
    """Your receiver. Hands back the reassembled bytes via `.data()`."""

    def __init__(self, data_channel, ack_channel):
        self.data_channel = data_channel
        self.ack_channel = ack_channel
        self.expected = 0         # next piece we can hand to the application
        self.buffer = {}          # seq -> payload that arrived early
        self.out = bytearray()

    def step(self):
        packet = self.data_channel.receive()
        if packet is None:
            return
        kind, seq, payload = packet
        if kind != "DATA":
            return
        # R3: a piece we already delivered or already buffered is not written
        #     twice - the copy is only acknowledged again.
        if seq >= self.expected and seq not in self.buffer:
            self.buffer[seq] = payload
            # R2: hand pieces over strictly in order; early ones wait here.
            while self.expected in self.buffer:
                self.out += self.buffer.pop(self.expected)
                self.expected += 1
        # ACK every DATA we see, even an old duplicate: if a duplicate
        # arrives, our earlier ACK may have been the thing that got lost.
        self.ack_channel.send(("ACK", seq, self.expected))

    def data(self):
        """The bytes reassembled so far."""
        return bytes(self.out)


# ------------------------------------------------------------------- harness
def verify(seed=246, size=2000, max_steps=200_000):
    original = bytes(random.Random(seed).getrandbits(8) for _ in range(size))
    up, down = UnreliableChannel(seed), UnreliableChannel(seed + 1)

    # Data goes out over `up`, ACKs come back over `down`. Both are unreliable.
    sender = Sender(up, down, original)
    receiver = Receiver(up, down)

    for _ in range(max_steps):
        alive = sender.step()
        receiver.step()
        if not alive and len(receiver.data() or b"") >= size:
            break

    got = receiver.data() or b""
    ok = hashlib.sha256(got).hexdigest() == hashlib.sha256(original).hexdigest()
    print(f"  bytes    sent {size}   received {len(got)}")
    print(f"  channel  {up.stats}")
    print(f"  result   {'IDENTICAL' if ok else 'CORRUPTED OR INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--seed", type=int, default=246)
    a = p.parse_args()
    raise SystemExit(verify(a.seed) if a.verify else p.print_help())
