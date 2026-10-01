# Task 2 Report

## 1. CDN Analysis Table
| Site | Chain Length | Final Zone | Third Party? | My Rule's Verdict |
|---|---|---|---|---|
| www.microsoft.com | 3 | e13678.dscb.akamaiedge.net | Yes | Yes |
| www.netflix.com | 2 | www.prod.ftl.netflix.com | No | Yes |
| www.adobe.com | 3 | a1319.dscr.akamai.net | Yes | Yes |
| www.cnn.com | 2 | cnn-tls.map.fastly.net | Yes | Yes |
| www.apple.com | 4 | e6858.dsce9.akamaiedge.net | Yes | Yes |
| www.korea.ac.kr | 1 | www.korea.ac.kr | No | No |
| www.stanford.edu | 2 | stanford.netlifyglobalcdn.com | Yes | Yes |
| www.bbc.co.uk | 3 | bbc.map.fastly.net | Yes | Yes |
| www.spotify.com | 2 | atc.spotify.map.fastly.net | Yes | Yes |
| www.github.com | 2 | github.com | No | Yes |
| www.wikipedia.org | 2 | dyna.wikimedia.org | No | Yes |
| www.nytimes.com | 4 | nytimes.map.fastly.net | Yes | Yes |

## 2. Third-Party Classification Rule (Part B4)
* **My Rule :** CNAME의 마지막 도메인과 원래 도메인의 이름이 다르면 서드파티 CDN이라고 판정했다.
* **The site it got wrong :** netflix.com, github.com, wikipedia.org
* **Why it got wrong :** 이 사이트들은 자체 인프라를 사용하지만,단순 문자열 비교 규칙을 적용한 내 규칙으로는 CNAME 구조상 주소 이름만 바뀐 사이트들까지 서드파티(Yes)로 잘못 판정하게 된다.

## 3. DNS Steering Number (Part B5)
* **Networks tested:** Mac Wi-Fi  vs iPhone Hotspot
* **Resolvers tested:** system resolver, Google (8.8.8.8), Quad9 (9.9.9.9)
* **Steering number (resolver):** 7 of 8 third-party CDN sites answered differently to a different resolver (microsoft, adobe, cnn, apple, bbc, spotify, nytimes. stanford만 세 resolver 모두 같은 주소).
* **Steering number (network):** 3 of 8 third-party CDN sites answered differently on a different network (Wi-Fi vs Hotspot, 같은 resolver 기준: microsoft, adobe, apple).


## 4. Part A Packet Capture Results
* **A2 (Query/Response pair):** 패킷 1(질의) ↔ 패킷 2(응답), 둘 다 Transaction ID 0x4cf0
* **A3 (Delegation & Answer packets):** 위임 응답 = 패킷 2 (198.41.0.4 루트 서버, ID 0x4cf0, Answer 0 / Authority NS 6 / Additional 10), 최종 응답 = 패킷 6 (163.152.11.6, ID 0xbb25, Answer A 1개)
* **A4 (Largest Packet Size):** (383 bytes) - 해당 위임 패킷은 단순히 하나의 IP 주소만 반환하는 것이 아니라, Authority 섹션과 Additional 섹션에 다음에 찾아가야 할 네임서버들의 도메인 이름과 IP 주소(Glue records) 등 부가 정보가 한꺼번에 묶여서 전달되기 때문에 패킷의 용량이 커진 것이다.