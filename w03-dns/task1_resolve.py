#!/usr/bin/env python3
"""Week 3 · Task 1 — Build your own iterative resolver.

Textbook §2.4.2 - §2.4.3.

`dig +trace` walks root -> TLD -> authoritative for you. In this task you do
that walk yourself: start at a root server, read the delegation it returns,
ask the next server, and keep going until somebody answers authoritatively.

You may shell out to `dig` for the transport, or use a DNS library
(`dnspython` is in the container). Either is fine - what matters is that
*you* follow the delegations rather than letting a tool do it.

    python3 task1_resolve.py www.korea.ac.kr
    python3 task1_resolve.py --verify        # check yourself against dig

Pass condition
--------------
`--verify` resolves five names with your resolver and with `dig`, and the
addresses must agree. A name behind a CDN may legitimately return a different
address each time; the harness compares the *set of authoritative nameservers*
you ended at for those, not the address.
"""
import argparse, subprocess, sys

import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.query
import dns.rcode
import dns.rdatatype

# Root servers. Everything starts here; there is no earlier step.
ROOT_SERVERS = [
    "198.41.0.4",       # a.root-servers.net
    "199.9.14.201",     # b.root-servers.net
    "192.33.4.12",      # c.root-servers.net
]

# (name, kind).  "stable" names must match dig exactly.  "cdn" names are served
# from many replicas and may legitimately give you a different address than dig
# got a second earlier - for those we only require that you reached an answer.
VERIFY_NAMES = [
    ("www.korea.ac.kr", "stable"),
    ("dns.google", "stable"),
    ("en.wikipedia.org", "stable"),
    ("www.stanford.edu", "stable"),
    ("www.microsoft.com", "cdn"),
]


class Resolver:
    """Your iterative resolver.

    The whole point is that you never ask a server to recurse for you.
    You ask one server, it says "not mine, ask over there", and you go there.

    Suggested shape - but it is yours to design:

        resolve(name) -> (address, path)
            address : the A record you ended up with, as a string
            path    : the servers you asked, in order, so you can show your work

    Things you will hit, in roughly this order:

    1.  A delegation gives you NS *names*, sometimes with glue A records and
        sometimes without. No glue means you have to resolve that nameserver's
        name first - which is another walk. Decide what you do there.
    2.  A server may not answer. Try the next one rather than giving up.
    3.  CNAMEs. The answer you get back may be a different name than the one
        you asked for, and you have to start again with that name.
    4.  Loops. Cap your depth.

    If you shell out to dig, the flag you want is `+norecurse`, so that the
    server you ask replies with a delegation instead of doing the work:

        dig @198.41.0.4 www.korea.ac.kr +norecurse
    """

    MAX_DEPTH = 30
    MAX_QUERIES = 200
    TIMEOUT = 2.0

    def resolve(self, name):
        """Return an IPv4 address and every server contacted, including failures."""
        qname = dns.name.from_text(name, origin=dns.name.root)
        path = []
        self._queries = 0
        address = self._resolve(qname, path, 0, set())
        return address, path

    def _resolve(self, qname, path, depth, active_names):
        # This set also catches a nameserver whose address depends on itself.
        if depth >= self.MAX_DEPTH or qname in active_names:
            raise RuntimeError(f"DNS lookup loop or depth limit at {qname}")
        active_names.add(qname)
        tried = set()

        def follow(servers, level):
            if depth + level >= self.MAX_DEPTH:
                raise RuntimeError(f"DNS delegation depth limit at {qname}")

            for address, ns_name in servers:
                if address is None:
                    # An NS record is only a name. Resolve its A record by
                    # making a separate, nonrecursive walk from the roots.
                    try:
                        address = self._resolve(ns_name, path,
                                                depth + level + 1, active_names)
                    except (LookupError, RuntimeError):
                        continue

                if address in tried:
                    continue
                tried.add(address)
                if self._queries >= self.MAX_QUERIES:
                    raise RuntimeError("DNS query limit exceeded")
                self._queries += 1
                path.append(address)

                query = dns.message.make_query(qname, dns.rdatatype.A)
                query.flags &= ~dns.flags.RD  # Never ask an upstream to recurse.
                try:
                    reply = dns.query.udp(query, address, timeout=self.TIMEOUT)
                    if reply.flags & dns.flags.TC:
                        reply = dns.query.tcp(query, address, timeout=self.TIMEOUT)
                except (dns.exception.DNSException, OSError):
                    continue

                if reply.rcode() == dns.rcode.NXDOMAIN and reply.flags & dns.flags.AA:
                    raise LookupError(f"{qname} does not exist")
                if reply.rcode() != dns.rcode.NOERROR:
                    continue

                if reply.flags & dns.flags.AA:
                    for rrset in reply.answer:
                        if rrset.name == qname and rrset.rdtype == dns.rdatatype.A:
                            return rrset[0].address
                    for rrset in reply.answer:
                        if rrset.name == qname and rrset.rdtype == dns.rdatatype.CNAME:
                            # Even if this packet also contains the target's A
                            # record, start a fresh trace at the roots.
                            return self._resolve(rrset[0].target, path,
                                                 depth + level + 1, active_names)

                delegations = [rrset for rrset in reply.authority
                               if rrset.rdtype == dns.rdatatype.NS
                               and qname.is_subdomain(rrset.name)]
                if not delegations:
                    continue
                delegation = max(delegations, key=lambda rrset: len(rrset.name))
                ns_names = [record.target for record in delegation]
                glue = [record.address
                        for rrset in reply.additional
                        if rrset.rdtype == dns.rdatatype.A
                        and rrset.name in ns_names
                        for record in rrset]
                # Try every supplied address first. Names remain as fallbacks
                # for absent or stale glue, and for servers that do not reply.
                next_servers = [(ip, None) for ip in glue]
                next_servers += [(None, ns_name) for ns_name in ns_names]
                try:
                    return follow(next_servers, level + 1)
                except LookupError:
                    # Another server at this level may have usable delegation.
                    continue

            raise LookupError(f"No server could resolve {qname}")

        try:
            return follow([(ip, None) for ip in ROOT_SERVERS], 0)
        finally:
            active_names.remove(qname)


# ------------------------------------------------------------------- harness
def dig_answer(name):
    """What the system resolver says, for comparison."""
    out = subprocess.run(["dig", "+short", name, "A"],
                         capture_output=True, text=True).stdout
    return [l for l in out.split() if l and l[0].isdigit()]


def verify():
    r, failures = Resolver(), 0
    for name, kind in VERIFY_NAMES:
        try:
            addr, path = r.resolve(name)
        except NotImplementedError:
            print("Nothing implemented yet - write Resolver.resolve first.")
            return 1
        except Exception as e:
            print(f"  FAIL  {name:<22} your resolver raised {e!r}")
            failures += 1
            continue
        expected = dig_answer(name)
        if addr in expected:
            note = ""
        elif kind == "cdn":
            note = "  <- differs, but this name is CDN-hosted. Explain it."
        else:
            note = "  <- should have matched"
            failures += 1
        print(f"  {'FAIL' if note.endswith('matched') else 'ok  '}  {name:<22} "
              f"you={addr:<16} dig={','.join(expected) or '-'}   "
              f"hops={len(path)}{note}")
    print(f"\n  {len(VERIFY_NAMES) - failures}/{len(VERIFY_NAMES)} ok")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", default="www.korea.ac.kr")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()

    if a.verify:
        sys.exit(verify())

    addr, path = Resolver().resolve(a.name)
    for i, server in enumerate(path, 1):
        print(f"  {i}. asked {server}")
    print(f"\n  {a.name} -> {addr}")


if __name__ == "__main__":
    main()
