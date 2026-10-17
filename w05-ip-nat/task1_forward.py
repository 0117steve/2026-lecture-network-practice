#!/usr/bin/env python3
"""Week 5 · Task 1 — Subnets and longest-prefix match.

Textbook §4.3.2 (IPv4 addressing, CIDR) and §4.3.3 (forwarding).

Two things a router does with every packet: work out which prefixes the
destination falls inside, and pick the longest one. The second is the whole
of "longest prefix match", and it is the reason the internet's routing table
can hold a million entries and still be answerable.

You build both, from integers up. No `ipaddress` module - that library is
exactly the thing you are supposed to understand this week.

    python3 task1_forward.py --verify
"""
import argparse


ALL_ONES = 0xFFFFFFFF


def ip_to_int(text):
    """'10.20.30.70' -> 32-bit int, built with shifts."""
    parts = text.strip().split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a dotted-quad address: {text!r}")
    value = 0
    for p in parts:
        octet = int(p)
        if octet > 255:
            raise ValueError(f"octet out of range in {text!r}")
        value = (value << 8) | octet
    return value


def int_to_ip(value):
    """32-bit int -> '10.20.30.70'."""
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def mask_of(prefix_len):
    """/24 -> 0xFFFFFF00. /0 -> 0."""
    return (ALL_ONES << (32 - prefix_len)) & ALL_ONES


def parse_cidr(cidr):
    """'163.152.6.0/24' -> (network as int, prefix length).

    Requirements: reject a prefix length outside 0-32, and reject an address
    whose host bits are set when they should not be (163.152.6.5/24 is a
    common way to write a host, but it is not a network).
    """
    addr_text, sep, len_text = cidr.strip().partition("/")
    if not sep or not len_text.isdigit():
        raise ValueError(f"missing prefix length: {cidr!r}")
    prefix_len = int(len_text)
    if not 0 <= prefix_len <= 32:                         # R1
        raise ValueError(f"prefix length {prefix_len} outside 0-32")
    address = ip_to_int(addr_text)
    if address & ~mask_of(prefix_len) & ALL_ONES:         # R2: host bits set
        raise ValueError(f"{cidr} has host bits set - that is a host, not a network")
    return address, prefix_len


def network_range(cidr):
    """'163.152.6.0/24' -> (first usable, last usable, broadcast) as strings.

    Careful at the edges. /31 and /32 do not have a usable host range in the
    ordinary sense - decide what you return and say so in observation.md.

    What this returns at the edges:
      /31  both addresses are usable (RFC 3021 point-to-point link), and there
           is no broadcast address -> (first, second, None)
      /32  one address, the host itself, no broadcast -> (it, it, None)
    """
    network, prefix_len = parse_cidr(cidr)
    broadcast = network | (~mask_of(prefix_len) & ALL_ONES)
    if prefix_len == 32:
        return int_to_ip(network), int_to_ip(network), None
    if prefix_len == 31:
        return int_to_ip(network), int_to_ip(broadcast), None
    return int_to_ip(network + 1), int_to_ip(broadcast - 1), int_to_ip(broadcast)


class ForwardingTable:
    """Longest-prefix-match forwarding.

    add(cidr, next_hop)  ·  lookup(address) -> next_hop or None

    The default route 0.0.0.0/0 matches everything and is the shortest prefix,
    so it must lose to any other match. If two entries have the same prefix
    length, the table is malformed - say what you do.

    Same network and same length added twice: the later one replaces the
    earlier one, the way a routing update replaces an old route.
    """

    def __init__(self):
        self.routes = {}          # (network, prefix_len) -> next_hop

    def add(self, cidr, next_hop):
        self.routes[parse_cidr(cidr)] = next_hop

    def lookup(self, address):
        target = ip_to_int(address) if isinstance(address, str) else address
        best_len, best_hop = -1, None
        for (network, prefix_len), hop in self.routes.items():
            if target & mask_of(prefix_len) == network and prefix_len > best_len:
                best_len, best_hop = prefix_len, hop               # R4, R5
        return best_hop


# ------------------------------------------------------------------- harness
RANGE_CASES = [
    ("192.168.0.0/24",  "192.168.0.1",   "192.168.0.254",  "192.168.0.255"),
    ("10.0.0.0/8",      "10.0.0.1",      "10.255.255.254", "10.255.255.255"),
    ("172.16.32.0/20",  "172.16.32.1",   "172.16.47.254",  "172.16.47.255"),
    ("203.0.113.64/26", "203.0.113.65",  "203.0.113.126",  "203.0.113.127"),
]

TABLE = [
    ("0.0.0.0/0",       "default-gw"),
    ("10.0.0.0/8",      "campus"),
    ("10.20.0.0/16",    "eng-building"),
    ("10.20.30.0/24",   "lab-floor"),
    ("10.20.30.64/26",  "lab-rack-2"),
    ("192.168.1.0/24",  "home"),
]

LOOKUP_CASES = [
    ("10.20.30.70",   "lab-rack-2"),     # inside all four 10.x entries
    ("10.20.30.10",   "lab-floor"),
    ("10.20.99.1",    "eng-building"),
    ("10.99.0.1",     "campus"),
    ("8.8.8.8",       "default-gw"),
    ("192.168.1.77",  "home"),
]


def verify():
    fails = 0
    for cidr, first, last, bcast in RANGE_CASES:
        try:
            got = network_range(cidr)
        except NotImplementedError:
            print("  network_range is still a stub"); return 1
        except Exception as e:
            print(f"  FAIL  {cidr:<18} raised {e!r}"); fails += 1; continue
        ok = tuple(got) == (first, last, bcast)
        print(f"  {'ok  ' if ok else 'FAIL'}  {cidr:<18} {got}")
        fails += not ok

    t = ForwardingTable()
    try:
        for cidr, hop in TABLE:
            t.add(cidr, hop)
    except NotImplementedError:
        print("  ForwardingTable is still a stub"); return 1

    for addr, expect in LOOKUP_CASES:
        got = t.lookup(addr)
        ok = got == expect
        print(f"  {'ok  ' if ok else 'FAIL'}  {addr:<16} -> {got}  (want {expect})")
        fails += not ok

    print(f"\n  {len(RANGE_CASES) + len(LOOKUP_CASES) - fails}"
          f"/{len(RANGE_CASES) + len(LOOKUP_CASES)} ok")
    return 1 if fails else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    raise SystemExit(verify() if a.verify else p.print_help())
