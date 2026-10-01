#!/usr/bin/env python3
"""Week 3 · Task 2 — Does DNS actually steer you? Measure it.

Textbook §2.4.3 (records) and §2.5 (CDNs).

The lecture claims two things:

    (a) most large sites are served by a CDN, reached through a CNAME chain
    (b) DNS steers each user to a *nearby* replica

Both are testable from your laptop, and one of them is harder to prove than
the slide makes it look. Your job is to produce the evidence and a number.

    python3 task2_steering.py --collect        # gather the raw data
    python3 task2_steering.py --report         # your analysis

What you have to build
----------------------
1.  For each hostname in SITES, follow the CNAME chain to its end and record
    every hop. `--collect` should leave the raw data in out/chains.json.

2.  Decide, for each site, whether it is served by a **third party**.
    This is the hard part and there is no single right answer:

      - `www.microsoft.com` ends at `akamaiedge.net`     - clearly third party
      - `www.netflix.com`   stops inside `netflix.com`   - own CDN, not third party
      - some sites have no CNAME at all and still sit behind a CDN (anycast)
      - `foo.cloudfront.net` and `foo.s3.amazonaws.com` are both Amazon,
        but they are not the same service

    Write down the rule you used and **defend it in observation.md**. A rule
    that just compares the last two labels will be wrong on at least one of
    the sites below; find which, and say so.

3.  Ask **two different resolvers** for the same name and compare the
    addresses you get back. If DNS really steers by location, a CDN-hosted
    name should answer differently to resolvers sitting in different places.

        RESOLVERS below has your system resolver and two public ones.

    Report: of N CDN-hosted sites, how many returned a different address set
    from a different resolver? Claim (b) predicts most of them. Check it.

Pass condition
--------------
There is no fixed answer. You pass by producing, in out/report.md:

  - the table: site | chain length | final zone | third party? | your rule's verdict
  - the steering number: "X of N sites answered differently to a different resolver"
  - at least one site where your classification rule was wrong, and why
"""
import argparse, json, os

import dns.exception
import dns.resolver

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

SITES = [
    "www.microsoft.com",     # Akamai, multi-hop
    "www.netflix.com",       # own CDN
    "www.adobe.com",
    "www.cnn.com",
    "www.apple.com",
    "www.korea.ac.kr",       # no CDN at all
    "www.stanford.edu",
    "www.bbc.co.uk",
    "www.spotify.com",
    "www.github.com",
    "www.wikipedia.org",
    "www.nytimes.com",
]

RESOLVERS = {
    "system": None,          # whatever is in your resolv.conf
    "google": "8.8.8.8",
    "quad9":  "9.9.9.9",
}


MAX_CNAME_HOPS = 30


def make_resolver(server):
    """Use the system DNS configuration or one specified DNS server."""
    resolver = dns.resolver.Resolver(configure=server is None)
    if server is not None:
        resolver.nameservers = [server]
    resolver.timeout = 2.0
    resolver.lifetime = 5.0
    return resolver


def trace_cname_chain(name, resolver):
    """Return ordered names from the original hostname through the last CNAME.

    An absent CNAME ends the chain. Keep the partial chain and an error if a
    lookup fails or the DNS data contains a loop.
    """
    chain = [name.rstrip(".").lower()]
    seen = set(chain)
    for _ in range(MAX_CNAME_HOPS):
        try:
            answer = resolver.resolve(chain[-1], "CNAME", raise_on_no_answer=False)
        except (dns.exception.DNSException, OSError) as exc:
            return chain, f"{type(exc).__name__}: {exc}"

        if answer.rrset is None:
            return chain, None
        target = answer.rrset[0].target.to_text(omit_final_dot=True).lower()
        chain.append(target)
        if target in seen:
            return chain, f"CNAME loop at {target}"
        seen.add(target)

    return chain, f"CNAME chain exceeded {MAX_CNAME_HOPS} hops"


def lookup_addresses(name, resolver):
    """Return the distinct IPv4 answers for the original site name."""
    try:
        answer = resolver.resolve(name, "A")
    except (dns.exception.DNSException, OSError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    return sorted({record.address for record in answer}), None


def collect():
    """Gather CNAME chains and each resolver's A set into out/chains.json."""
    resolvers = {label: make_resolver(server)
                 for label, server in RESOLVERS.items()}
    results = {}
    for site in SITES:
        chain, chain_error = trace_cname_chain(site, resolvers["system"])
        entry = {"cname_chain": chain, "addresses": {}, "errors": {}}
        if chain_error:
            entry["errors"]["cname_chain"] = chain_error

        for label, resolver in resolvers.items():
            addresses, error = lookup_addresses(site, resolver)
            entry["addresses"][label] = addresses
            if error:
                entry["errors"][label] = error
        results[site] = entry

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "chains.json"), "w", encoding="utf-8") as output:
        json.dump(results, output, indent=2, ensure_ascii=False)
        output.write("\n")


def report():
    """Read out/chains.json and produce out/report.md.

    You write this too - including the classification rule that decides
    whether a site is on a third-party CDN.
    """
    raise NotImplementedError("build the report")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--collect", action="store_true")
    p.add_argument("--report", action="store_true")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.collect:
        collect()
    elif a.report:
        report()
    else:
        p.print_help()
