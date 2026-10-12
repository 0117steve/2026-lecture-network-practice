#!/usr/bin/env python3
"""Week 4 · Task 3 — Beat the fixed window.

Textbook §3.7.

`FixedWindow` is a sender that never adapts. It picks a window and keeps it,
forever, no matter what the network says back. It is not a strawman: it is what
you get if you skip congestion control entirely, and it was the internet's
actual failure mode in October 1986.

Write `YourControl` and beat it on the harness:

    python3 bench.py
    python3 bench.py --yours

The interface is two events and one number:

    .window        how many packets you are willing to have in flight
    .on_ack()      one packet made it there and back
    .on_loss()     a packet was dropped, or timed out waiting for its ACK

That is all the information a real TCP sender has. It cannot see the queue,
it cannot see the link rate, and neither can you. You infer them from these
two events, which is the entire idea of §3.7.
"""


class FixedWindow:
    """Send 64 packets at a time and never listen."""

    def __init__(self):
        self.window = 64

    def on_ack(self):
        pass

    def on_loss(self):
        pass


class YourControl:
    """Your congestion control.

    Things worth knowing before you start:

    * The link drains one packet per slot and the round trip is 20 slots, so
      the pipe holds about 20 packets. Above that you are only filling a queue.
    * The queue is 10 packets deep and drops from the tail. Filling it does not
      make you faster - it makes you slower, and everybody behind you too.
    * Cutting hard on every loss costs you throughput. Not cutting costs you
      correctness. §3.7 is the argument about where between those to sit.
    * You are allowed to grow differently before and after your first loss.
      That distinction has a name in the textbook.
    """

    # Reno-style AIMD with three changes:
    #
    # 1. One cut per congestion event. Losses show up only as timeouts, so a
    #    single overflow of the queue arrives as a burst of on_loss() calls,
    #    one per dropped packet. Packets that were already in flight when we
    #    cut cannot tell us anything new, so the next `window` events after a
    #    cut are counted off without cutting again (the idea behind NewReno).
    # 2. A gentler cut. Loss starts at about pipe + queue = 20 + 10 = 30
    #    packets. Halving lands at 15, well under the 20 the pipe needs, and the
    #    link sits idle. 0.6 x 30 = 18 lands just under the pipe instead.
    # 3. Slow probing after that: +0.1 packet per round trip instead of +1, so
    #    the window spends its time near the pipe size, not in the queue.
    BETA = 0.6          # multiplicative decrease
    INCREASE = 0.1      # additive increase, packets per round trip

    def __init__(self):
        self.window = 1.0
        self.slow_start = True     # until the first loss: +1 per ACK (doubling)
        self.recovery_left = 0     # events still owed to packets sent before the cut

    def on_ack(self):
        if self.recovery_left:
            self.recovery_left -= 1
        if self.slow_start:
            self.window += 1
        else:
            self.window += self.INCREASE / self.window   # ~INCREASE per RTT

    def on_loss(self):
        if self.recovery_left:
            # Same congestion event as the cut we already made.
            self.recovery_left -= 1
            return
        self.slow_start = False
        self.recovery_left = int(self.window)   # roughly what was in flight
        self.window = max(2.0, self.window * self.BETA)
