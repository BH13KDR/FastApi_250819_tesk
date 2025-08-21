EdgeDB 
EdgeDB = PostgreSQL 기반 차세대 DB + ORM 대체제 + 강력한 쿼리 언어(EdgeQL)
특징: "개발자 경험"과 "성능" 중심 설계

| 특징                  | 설명                              | MySQL/ORM 대비 장점                        |
| ------------------- | ------------------------------- | -------------------------------------- |
| **PostgreSQL 기반**   | 내부적으로 PostgreSQL 엔진 사용          | 안정성과 성능 보장                             |
| **EdgeQL**          | SQL보다 간결하고 객체지향적인 쿼리 언어         | 복잡한 JOIN 없이 직관적 쿼리 가능                  |
| **ORM 불필요**         | EdgeDB 클라이언트가 자동으로 Python 객체 생성 | SQLAlchemy, Tortoise 등 ORM 없이 코드 작성 가능 |
| **Code Generation** | `.edgeql` → 자동으로 Python 함수 생성   | 타입 안정성과 개발 속도 ↑                        |
| **성능**              | PostgreSQL + 최적화된 EdgeQL 엔진     | ORM보다 빠름                               |
| **유연한 모델링**         | 테이블 대신 `type` 개념 사용             | 링크(link)와 멀티 관계 모델링 쉬움                 |

설치법 
```bash
# CLI 설치
curl --proto '=https' --tlsv1.2 -sSf https://sh.edgedb.com | sh
# 버전 확인
edgedb --version

```
VS Code 설정

EdgeDB 전용 확장 설치 → magicstack.edgedb
EdgeQL 쿼리 지원, 자동완성, 스키마 탐색 가능

프로젝트 초기화
```bash
# 새 프로젝트 생성
edgedb project init
```

기본 스키마 정의
```edgeql
module default {
    type Person {
        required name: str;
    }

    type Movie {
        title: str;
        multi actors: Person;
    }
}
```
| EdgeDB     | MySQL         | 설명                         |
| ---------- | ------------- | -------------------------- |
| `type`     | `table`       | 테이블 대신 `type` 사용           |
| `required` | `NOT NULL`    | 값이 반드시 있어야 함               |
| `link`     | `FOREIGN KEY` | 관계 설정. `multi` vs `single` |
| `multi`    | `1:N` 관계      | 여러 개 참조 가능                 |
| `single`   | `1:1` 관계      | 단일 참조만 가능                  |


마이그레이션
```bash
# 마이그레이션 생성
edgedb migration create
# 적용
edgedb migrate
```

CRUD 예시

```edgeql
# INSERT
insert Movie {
    title := "Dune"
};

# UPDATE
update Movie
filter .title = "Dune"
set {
    actors := {
        (insert Person { name := "Timothee Chalamet" }),
        (insert Person { name := "Zendaya" })
    }
};

# SELECT
select Movie {
    title,
    actors: { name }
};

# DELETE
delete Movie
filter .title = "Dune";
```
EdgeDB + Python 연동
```bash
poetry add edgedb==2.2.0
```

스키마 예시 (Meeting)
```edgeql
module default {
    abstract type Auditable {
        required created_at -> cal::local_datetime {
            readonly := true;
            default := cal::to_local_datetime(datetime_current(), 'Asia/Seoul');
        }
    }

    type Meeting extending Auditable {
        required url_code: str {
            constraint exclusive;
            readonly := true;
        };
    }
}
```
abstract type → 상속 전용
readonly → 생성 시에만 값 설정 가능, 이후 변경 불가
constraint exclusive → 유니크 제약 + 자동 인덱스 생성

EdgeQL 쿼리 → Python 코드 생성
```bash
poetry run edgedb-py
```
→ .edgeql 쿼리를 자동으로 Python 함수로 변환해줌.

FastAPI 서비스 연동 예시

#services/meeting_service_edgedb.py
```python
import uuid
from app.queries.meeting.create_meeting_async_edgeql import create_meeting
from app.utils.edge import edgedb_client
from app.utils.base62 import Base62

async def service_create_meeting_edgedb():
    return await create_meeting(
        executor=edgedb_client,
        url_code=Base62.encode(uuid.uuid4().int),
    )
```
#apis/v1/meeting_router.py
```python
from fastapi import APIRouter
from app.services.meeting_service_edgedb import service_create_meeting_edgedb

edgedb_router = APIRouter(prefix="/v1/edgedb/meetings", tags=["Meeting"])

@edgedb_router.post("")
async def api_create_meeting_edgedb():
    return await service_create_meeting_edgedb()
```

테스트 및 CI 연동
#httpx + pytest 사용
```python
import httpx
from httpx import AsyncClient
from starlette.status import HTTP_200_OK
from app import app
from app.utils.edge import edgedb_client

async def test_api_create_meeting_edgedb():
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post("/v1/edgedb/meetings")

    assert response.status_code == HTTP_200_OK
    url_code = response.json()["url_code"]
    assert await edgedb_client.query_single(
        f"select exists (select Meeting filter .url_code = '{url_code}');"
    ) is True
```

GitHub Actions 연동

#.github/workflows/ci.yml
```python
- name: Setup edgedb
  uses: edgedb/setup-edgedb@v1

- name: Run tests
  run: |
    poetry run coverage run -m pytest .
    poetry run coverage report -m
```
| 구분        | MySQL                      | EdgeDB                       |
| --------- | -------------------------- | ---------------------------- |
| 테이블 명칭    | `table`                    | `type`                       |
| 관계 설정     | `FOREIGN KEY`              | `link`                       |
| ORM 필요 여부 | 필요(SQLAlchemy, Tortoise 등) | 불필요                          |
| 쿼리 언어     | SQL                        | EdgeQL                       |
| 쿼리 반환값    | dict / model               | Python 객체                    |
| 코드 생성     | 없음                         | 자동 Python 코드 생성              |
| 성능        | 표준적                        | PostgreSQL + 최적화 → ORM 대비 빠름 |
