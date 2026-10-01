TASK1 observation
반복적 리졸버가 모든 검증을 통과했고, 일반 도메인과 달리 CDN 기반 도메인들은 트래픽 분산을 위해 매 질의마다 다수의 IP를 번갈아 반환하므로, 리졸버와 시스템 명령어 간의 IP 순서 불일치가 발생하는 것이 정상임을 확인했다.

Why did the root server not simply hand you the address?


루트 서버는 모든 도메인 주소를 알 수 없기 때문이다. 대신 .kr이나 .com 같은 도메인(TLD)을 관리하는 서버의 위치만 알려주며 책임을 위임하는 DNS 계층 구조 때문이다. 


What did you do when a delegation arrived without glue, and how many extra lookups did that cost you?


다음 서버의 이름(NS)만 알고 IP를 모르는 상태이므로, 그 네임서버의 IP를 알아내기 위해 루트 서버부터 다시 새로운 DNS 질의가 필요하다. 이 과정에서 평소보다 3~4번의 추가 질의가 더 발생하게 된다. 

How many servers did you end up asking for one name? Compare that with the single question your laptop normally asks its resolver.


노트북은 평소 통신사 리졸버에 딱 1번만 질문(재귀 질의)하면 알아서 IP를 가져다주지만, 제작된 이 리졸버는 직접 3~6대의 서버를 찾아다녀야 했다

TASK2 observation
capture has queries and responses 항목 관련 문의드립니다. 컨테이너가 dns.flags.response 값을 0/1이 아니라 False/True로 출력하는데, 스크립트는 0/1만 세고 있어 정상 캡처도 0개로 나옵니다. 직접 실행해 보니 질의 7개, 응답 7개가 확인됩니다. 이 항목은 이대로 제출해도 될지 여쭤봅니다.

위임 응답과 최종 응답의 차이 (캡처에서 본 것)


둘은 같은 DNS 메시지 형식이고 채워진 섹션만 다르다. 2번 패킷(루트 198.41.0.4의 응답)은 Answer가 0개이고 Authority에 NS 6개, Additional에 글루 A 레코드가 들어 있으며 AA 플래그가 없다. 반면 6번 패킷(163.152.11.6의 응답)은 Answer에 A 레코드 1개가 있고 AA 플래그가 켜져 있는 권한 있는 최종 답이다.


서드파티 판정 규칙, 규칙이 틀린 사이트와 그 이유


CNAME 체인의 마지막 이름이 원래 이름과 다르면 서드파티로 판정했다. 이 규칙은 netflix, github, wikipedia를 서드파티로 잘못 판정했다. 세 곳 모두 이름은 바뀌지만 자기 소유 도메인(netflix.com, github.com, wikimedia.org) 안에서 끝나기 때문이다. 과제에서 말한 "마지막 두 라벨 비교" 규칙으로 바꿔도 wikipedia는 여전히 틀린다. wikipedia.org와 wikimedia.org는 문자열은 다르지만 같은 조직의 도메인이기 때문이다. 결국 문자열만으로는 소유자를 알 수 없다


Steering 숫자와 claim (b)를 지지하는지


서드파티 CDN 사이트 8개 중 resolver를 바꿨을 때 다른 주소를 받은 곳은 7개였다. 네트워크를 바꿨을 때(Mac Wi-Fi vs iPhone 핫스팟, 같은 resolver 기준) 다른 주소를 받은 곳은 3개였다(microsoft, adobe, apple). 따라서 DNS가 묻는 쪽에 따라 다른 복제 서버를 준다는 것은 확인했다. 하지만 "가까운" 복제 서버를 준다는 것까지는 증명하지 못했다. 두 네트워크가 모두 한국 안에 있어 위치 차이가 작고, 같은 quad9에 물어도 측정 시점에 따라 microsoft·adobe 주소가 달라졌다. 그래서 차이가 위치 때문인지 단순 부하 분산 때문인지 구분할 수 없다. 따라서 claim (b)는 부분적으로만 지지된다.

TASK3 observation

Baseline의 두 가지 문제점과 근본 원인
성능 문제 : 조회시 딕셔너리 대신 리스트를 사용하여 매번 데이터를 처음부터 끝까지 뒤져야 하는 선형 탐색을 수행해 속도가 매우 느리다.
정확성 문제 : 외부 서버가 알려주는 실제 유효기간(TTL)을 버리고, 무조건 60초 동안만 데이터를 유지하도록 되어 있다. 이로 인해 수명이 다한 쓰레기 데이터를 반환하는 버그가 발생하는 것이다.

최소 Upstream 횟수와 그 이유
275번 이다. 왜냐하면 캐시가 아무리 완벽하게 동작하더라도 반드시 외부에 요청해야 하는 필수 횟수가 정해져 있기 때문이다. 캐시가 비어있는 '최초 조회'시 무조건 외부 서버(Upstream)에 물어봐야 한다. 시뮬레이션이 진행되는 동안 각 데이터의 TTL이 만료될 때마다 최신화하기 위해 다시 물어봐야 한다. 이 필수적인 (최초 조회 + TTL 만료 갱신) 횟수의 합계가 275번이므로 절대 이 밑으로 내려갈 수 없다.

Baseline이 가장 엉망으로 처리하는 레코드와 그 이유
가장 엉망으로 처리되는 레코드는 TTL이 매우 짧은 CDN 레코드 또는 TTL이 매우 긴 루트 서버 레코드라고 볼 수 있다.
Baseline은 무조건 데이터를 60초 단위로 지우도록 설정되어 있다. 따라서 TTL이 20초인 레코드는 20초 만에 지워야 하는데 60초까지 들고 있으면서 40초 동안이나 잘못된 정보를 반환하게 만들고, TTL이 1일인 레코드는 하루 종일 들고 있어도 되는데 60초마다 멀쩡한 데이터를 지우고 다시 물어보게 만들어 쓸데없는 Upstream 횟수를 증폭시키기 때문이다.