[Best Dates 구현 정리 (조회 API)]
회의 일정 조회 API(/v1/mysql/meetings/{url_code})에서,
"가장 만나기 좋은 날짜(best_dates)" 상위 3개 날짜를 계산하여 응답

기존 API에 필드 추가 → 새로운 API 생성 하면 안됨
→ best_dates 필드를 GetMeetingResponse DTO에 추가 

[Best Dates 선정 기준]

정렬 우선순위 3단계

enabled 참가자 수가 많은 날짜 우선

enabled 수가 같다면, star 표시가 많은 날짜 우선

위 2개가 모두 같다면, 날짜가 빠른 순서로 정렬

Edge Case

날짜 범위가 3일 미만이면, 3개 미만으로 반환할 수도 있음.

전원이 **busy(=enabled=False)**인 경우에도, 날짜 오름차순으로 반환.

[구현 방식]
(1) GetMeetingResponse DTO 변경

파일 경로: app/dtos/get_meeting_response.py

① BestDate 클래스 추가
```python
import dataclasses
from typing import Iterable

@dataclasses.dataclass
class BestDate:
    date: date
    enable_count: int
    star_count: int
```

각 날짜별로 enable_count와 star_count를 저장.

dataclass로 관리 → mutable 객체로 카운팅 가능.

② best_dates 필드 추가
```python
class GetMeetingResponse(BaseModel):
    ...
    best_dates: list[date]
```

응답 모델에서 상위 3개의 날짜를 담는 필드.

③ _get_best_dates 메서드 구현
```python
@classmethod
def _get_best_dates(
    cls, participant_dates: Iterable[ParticipantDate | ParticipantDateModel]
) -> list[date]:
    result_dict: dict[date, BestDate] = {}

    # 날짜별 enable/star 카운트 집계
    for participant_date in participant_dates:
        if participant_date.date not in result_dict:
            result_dict[participant_date.date] = BestDate(
                date=participant_date.date,
                enable_count=0,
                star_count=0,
            )
        if participant_date.enabled:
            result_dict[participant_date.date].enable_count += 1
            if participant_date.starred:
                result_dict[participant_date.date].star_count += 1

    # 정렬 (enable ↓, star ↓, date ↑)
    result_list = list(result_dict.values())
    result_list.sort(
        key=lambda best_date: (
            -best_date.enable_count,
            -best_date.star_count,
            best_date.date,
        ),
    )

    # 상위 3개 날짜만 반환
    return [best_date.date for best_date in result_list[:3]]
```
    
정렬 로직
정렬 기준	방향
enable_count	내림차순 ↓
star_count	내림차순 ↓
date	오름차순 ↑

[팩토리 메서드에서 best_dates 계산]

① EdgeDB 전용
```python
@classmethod
def from_edgedb(cls, meeting: FullMeeting) -> GetMeetingResponse:
    return GetMeetingResponse(
        ...
        best_dates=cls._get_best_dates(
            (participant_date
                for participant in meeting.participants
                for participant_date in participant.dates)
        ),
    )
```


② MySQL 전용
```python
@classmethod
def from_mysql(cls, meeting: MeetingModel) -> GetMeetingResponse:
    return GetMeetingResponse(
        ...
        best_dates=cls._get_best_dates(
            (
                participant_date
                for participant in meeting.participants
                for participant_date in participant.participant_dates
            )
        ),
    )
```


[테스트 코드 (MySQL 기준)]

파일 경로: app/tests/apis/v1/test_best_dates_mysql.py

```python
class TestBestDatesMysql(TestCase):
    async def test_best_dates(self) -> None:
        """
        테스트 시나리오:
        - 2025-12-03 → 2명 모두 enable
        - 2025-12-10 → 2명 모두 enable + 1명 star
        - 2025-12-11 → 1명만 enable
        기대 결과: ["2025-12-10", "2025-12-03", "2025-12-11"]
        """

        # Given: 미팅 생성 및 참가자 2명 등록
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            create_meeting_response = await client.post(url="/v1/mysql/meetings")
            url_code = create_meeting_response.json()["url_code"]

            await client.patch(
                url=f"/v1/mysql/meetings/{url_code}/date_range",
                json={"start_date": "2025-12-01", "end_date": "2025-12-31"},
            )

            participant_response1 = await client.post(
                url="/v1/mysql/participants",
                json={"name": "test_name1", "meeting_url_code": url_code},
            )
            participant_response2 = await client.post(
                url="/v1/mysql/participants",
                json={"name": "test_name2", "meeting_url_code": url_code},
            )

            # 참가자 날짜 on/off 설정
            ...

            # When
            meeting_response = await client.get(url=f"/v1/mysql/meetings/{url_code}")

        # Then: best_dates 검증
        self.assertEqual(meeting_response.status_code, HTTP_200_OK)
        meeting_response_body = meeting_response.json()
        self.assertEqual(
            meeting_response_body["best_dates"],
            ["2025-12-10", "2025-12-03", "2025-12-11"],
        )
```


[동작 순서]

클라이언트 → /v1/mysql/meetings/{url_code} 요청

MySQL DB에서 미팅 및 참가자 날짜 정보 조회

GetMeetingResponse.from_mysql() 호출

_get_best_dates()로 best_dates 계산

best_dates 포함한 JSON 응답 반환

핵심 정리
| 포인트               | 설명                                           |
| ----------------- | -------------------------------------------- |
| **API 변경**        | 새로운 API 추가 ❌ → 기존 조회 API에 `best_dates` 필드 추가 |
| **Best Dates 선정** | enable ↓ → star ↓ → date ↑ 순으로 정렬            |
| **핵심 메서드**        | `_get_best_dates()`                          |
| **테스트 검증**        | 3개 날짜의 우선순위를 정확히 체크                          |
| **에지 케이스**        | 날짜가 3일 미만일 수 있음 / 전원 busy여도 날짜 순서로 반환        |



###[Locust 성능 테스트]

파이썬으로 구현된 부하 테스트(load testing) 도구

동시에 수천 ~ 수만 건의 요청을 발생시켜 API 성능을 측정 가능

API별 성공/실패율, 응답 속도(latency), RPS(Request Per Second) 등의 지표 제공

테스트 시나리오를 Python 코드로 작성 → 유연성 높음

HTTP뿐 아니라 WebSocket, gRPC 등 파이썬으로 호출 가능한 모든 것을 테스트 가능

[Locust 설치]
```bash
poetry add --group=dev locust==2.32.6
poetry add gunicorn==23.0.0
```
locust → 부하 테스트 실행 도구

gunicorn → uvicorn worker를 여러 개 실행하여 테스트 환경에서 실제 서버처럼 동작시키기 위해 사용

[Locust 시나리오 구현]

테스트 시나리오는 locu/locustfile.py에 작성합니다.
MySQL과 EdgeDB 각각에 대해 동일한 작업을 수행하는 성능 비교 테스트를 진행합니다.

locustfile.py
```python
from locust import HttpUser, task

class TortoiseUser(HttpUser):  # MySQL 사용자 시뮬레이션
    @task
    def get_and_update_and_get(self):
        # 1. 미팅 생성
        create_meeting_response = self.client.post("/v1/mysql/meetings")
        url_code = create_meeting_response.json()["url_code"]

        # 2. 날짜 범위 설정
        self.client.patch(
            url=f"/v1/mysql/meetings/{url_code}/date_range",
            json={"start_date": "2025-01-01", "end_date": "2025-02-20"},
            name="patch_date_range_mysql",
        )

        # 3. 참가자 추가
        self.client.post(
            url="/v1/mysql/participants",
            json={"name": "test_name", "meeting_url_code": url_code},
            name="post_participants_mysql",
        )

        # 4. 미팅 조회
        self.client.get(
            url=f"/v1/mysql/meetings/{url_code}",
            name="get_meetings_mysql",
        )


class EdgedbUser(HttpUser):  # EdgeDB 사용자 시뮬레이션
    @task
    def get_and_update_and_get(self):
        create_meeting_response = self.client.post("/v1/edgedb/meetings")
        url_code = create_meeting_response.json()["url_code"]

        self.client.patch(
            url=f"/v1/edgedb/meetings/{url_code}/date_range",
            json={"start_date": "2025-01-01", "end_date": "2025-02-20"},
            name="patch_date_range_edgedb",
        )

        self.client.post(
            url="/v1/edgedb/participants",
            json={"name": "test_name", "meeting_url_code": url_code},
            name="post_participants_edgedb",
        )

        self.client.get(
            url=f"/v1/edgedb/meetings/{url_code}",
            name="get_meetings_edgedb",
        )

```

[Locust 주요 개념]

| 개념                 | 설명                                          |
| ------------------ | ------------------------------------------- |
| **HttpUser**       | 가상의 사용자(User)를 시뮬레이션하는 클래스                  |
| **task**           | 한 사용자가 수행하는 작업 단위                           |
| **self.client**    | 내부적으로 `requests` 라이브러리를 사용하여 HTTP 요청 수행     |
| **name**           | Locust Web UI에서 API별 성능 데이터를 보기 쉽게 라벨링하는 옵션 |
| **사용자 수(users)**   | 동시에 요청을 발생시킬 가상 사용자 개수                      |
| **ramp up(스폰 속도)** | 초당 몇 명씩 사용자를 증가시킬지 설정                       |


[커넥션 풀 사이즈 조정]

공정한 비교를 위해 MySQL과 EdgeDB의 커넥션 풀 크기를 동일하게 설정.

```python
# app/configs/base_config.py
CONNECTION_POOL_MAXSIZE: int = 10
```
EdgeDB 기본 풀 크기가 10 → MySQL도 동일하게 설정

최대 커넥션 수 = worker 수 × pool size

[성능 테스트 실행]
서버 실행
```bash
gunicorn asgi:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

--workers 2: uvicorn worker 2개 실행

--worker-class: ASGI 환경 지원

Locust 실행
```bash
cd locu
locust
```

접속: http://localhost:8089

입력값 설정:

Number of users: 10

Spawn rate: 1 (1초에 1명씩 증가)

Host: http://127.0.0.1:8000

[성능 테스트 결과 해석]

Locust UI에서 확인할 핵심 지표는 다음과 같습니다:

##① p95 (95th Percentile)

95% 요청이 완료된 최대 시간

평균값보다 실전에서 더 유용한 지표

캐시 미스나 일시적 지연 문제를 감지 가능

예시:

100개의 요청 중 p95=100ms → 95개는 100ms 이내 처리, 5개는 100ms 이상 소요

##② RPS (Requests Per Second)

초당 처리한 요청 개수

RPS가 높을수록 서버가 많은 요청을 소화 가능

단, latency(응답 속도)와 반드시 반비례하지는 않음

예시:

API가 내부에서 await asyncio.sleep(1)을 수행하는 경우
→ latency = 1000ms지만 CPU 부하가 적으므로 RPS는 높을 수 있음

[EdgeDB 성능 개선]
문제점

EdgeDB에서 participant 생성 시 두 번의 쿼리 사용 → 성능 저하

해결책

쿼리를 트랜잭션 단위 1회로 최적화

app/queries/participant/create_participant_with_dates.edgeql

```sql
with
    name := <str>$name,
    url_code := <str>$url_code,
    dates := <array<cal::local_date>>$dates,
    PARTICIPANT := (
        insert Participant {
            name := name,
            meeting := (
                select Meeting filter .url_code = url_code
            )
        }
    ),
    DATES := (
        for date in array_unpack(dates)
        insert ParticipantDate {
            participant := PARTICIPANT,
            date := date,
        }
    ),
select DATES {id, participant};
```
트랜잭션 충돌 감소

재시도 및 jitter로 인한 latency 감소

EdgeDB 성능 대폭 향상 → RPS 증가

| 구분              | EdgeDB | MySQL |
| --------------- | ------ | ----- |
| **p95 latency** | 낮음 ✅   | 높음 ❌  |
| **RPS**         | 높음 ✅   | 낮음 ❌  |
| **동시성**         | 우수     | 보통    |

결론: EdgeDB가 대규모 트래픽에서 더 안정적

[정리]

Locust를 사용해 API 성능 병목 지점을 발견 가능

p95, RPS 등 핵심 지표 해석 방법 학습

EdgeDB 쿼리 최적화를 통해 성능 개선

시나리오 및 환경 설정에 따라 테스트 결과 달라짐