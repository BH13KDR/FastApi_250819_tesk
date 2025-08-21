1. Tortoise ORM + MySQL 연동: Django ORM과 매우 비슷
2. Aerich로 마이그레이션 관리
3. httpx로 FastAPI 비동기 API 테스트 작성
4. TDD 방식으로 개발 → 테스트 먼저 작성 후 구현
5. CI 환경에서 MySQL 세팅까지 자동화
6. 테스트 전략은 E2E 중심, DB까지 검증하는 테스트 추천

[필수 패키지]

poetry add "tortoise-orm[asyncmy]==0.23.0"
poetry add cryptography==44.0.0
poetry add aerich==0.8.1 tomlkit==0.13.2
poetry add pydantic_settings==2.7.1
poetry add httpx==0.28.1

[패키지 역할]

tortoise-orm :	Django ORM과 유사한 async ORM
cryptography :	MySQL 접속 시 비밀번호 암호화 지원
aerich :    Tortoise ORM용 마이그레이션 툴 (SQLAlchemy의 Alembic 같은 역할)
pydantic_settings :	.env 및 환경 변수 관리 (Pydantic v2 전용)
tomlkit	Aerich :    버그 때문에 별도 설치 필요
httpx :  FastAPI async API 테스트 클라이언트

[Tortoise ORM 설정]

#환경 설정 (app/configs/base_config.py)
```python
from enum import StrEnum
from pydantic_settings import BaseSettings

class Env(StrEnum):
    LOCAL = "local"
    STAGE = "stage"
    PROD = "prod"

class Config(BaseSettings):
    ENV: Env = Env.LOCAL

    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "1234"
    MYSQL_DB: str = "when2meet_vod"
```

# Tortoise 설정 (app/configs/tortoise_config.py)
```python
from fastapi import FastAPI
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise
from app.configs import config

TORTOISE_APP_MODELS = [
    "app.tortoise_models.meeting",
    "aerich.models",
]

TORTOISE_ORM = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.mysql",
            "credentials": {
                "host": config.MYSQL_HOST,
                "port": config.MYSQL_PORT,
                "user": config.MYSQL_USER,
                "password": config.MYSQL_PASSWORD,
                "database": config.MYSQL_DB,
                "connect_timeout": 5, #5초 이상 응답 없으면 연결 중단
                "maxsize": 30, #커넥션 풀 최대 개수
            },
        },
    },
    "apps": {
        "models": {"models": TORTOISE_APP_MODELS},
    },
    "timezone": "Asia/Seoul",
}

def initialize_tortoise(app: FastAPI) -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    register_tortoise(app, config=TORTOISE_ORM)
```
Gunicorn 사용 시 worker 수 × maxsize 만큼 DB 커넥션 사용됨

[모델 생성 및 Aerich 마이그레이션]
# 기본 모델 (app/tortoise_models/base_model.py)
```python
from tortoise import fields

class BaseModel:
    id = fields.BigIntField(primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=True)

```
# Meeting 모델 (app/tortoise_models/meeting.py)
```python
from tortoise import Model, fields
from app.tortoise_models.base_model import BaseModel

class MeetingModel(BaseModel, Model):
    url_code = fields.CharField(max_length=255, unique=True)

    class Meta:
        table = "meetings"

    @classmethod
    async def create_meeting(cls, url_code: str):
        return await cls.create(url_code=url_code)
```
Aerich 마이그레이션
```bash
aerich init -t app.configs.tortoise_config.TORTOISE_ORM
aerich init-db
```
[마이그레이션 순서]
1. 모델 작성
2. TORTOISE_APP_MODELS에 모델 경로 등록
3. Aerich 초기화 → DB 테이블 생성
4. 테이블 생성 여부 및 컬럼 타입까지 반드시 확인

[Pytest & httpx 테스트 환경 설정]
#테스트용 conftest (conftest.py)
```python
import asyncio
from unittest.mock import Mock, patch
import pytest
import pytest_asyncio
from tortoise.backends.base.config_generator import generate_config
from tortoise.contrib.test import finalizer, initializer
from app.configs import config
from app.configs.tortoise_config import TORTOISE_APP_MODELS

def get_test_db_config():
    tortoise_config = generate_config(
        db_url=f"mysql://{config.MYSQL_USER}:{config.MYSQL_PASSWORD}@{config.MYSQL_HOST}:{config.MYSQL_PORT}/test",
        app_modules={"models": TORTOISE_APP_MODELS},
        connection_label="models",
        testing=True,
    )
    tortoise_config["timezone"] = "Asia/Seoul"
    return tortoise_config

@pytest.fixture(scope="session", autouse=True)
def initialize():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with patch("tortoise.contrib.test.getDBConfig", Mock(return_value=get_test_db_config())):
        initializer(modules=TORTOISE_APP_MODELS)
    yield
    finalizer()
    loop.close()

@pytest_asyncio.fixture(autouse=True, scope="session")
def event_loop():
    pass
```
pytest가 생성하는 event loop를 막아야 함 → Tortoise ORM과 충돌 방지
테스트 전 DB 초기화 + 테스트 종료 후 커넥션 정리

[httpx 기반 API 테스트 작성]
# 테스트 코드 (app/tests/apis/v1/test_meeting_router_mysql.py)
```python
import httpx
from starlette.status import HTTP_200_OK
from tortoise.contrib.test import TestCase
from app import app
from app.tortoise_models.meeting import MeetingModel

class TestMeetingRouter(TestCase):
    async def test_api_create_meeting_mysql(self):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/v1/mysql/meetings")

        assert response.status_code == HTTP_200_OK
        url_code = response.json()["url_code"]
        assert (await MeetingModel.filter(url_code=url_code).exists()) is True
```
FastAPI 서버 실행 없이 ASGITransport로 직접 요청
DB까지 실제 검증가능 → TDD 방식

[Meeting API 구현]
#서비스 (app/services/meeting_service_mysql.py)
```python
import uuid
from app.tortoise_models.meeting import MeetingModel
from app.utils.base62 import Base62

async def service_create_meeting_mysql() -> MeetingModel:
    return await MeetingModel.create_meeting(Base62.encode(uuid.uuid4().int))
    
```
#라우터 (app/apis/v1/meeting_router.py)
```python
from fastapi import APIRouter
from app.dtos.create_meeting_response import CreateMeetingResponse
from app.services.meeting_service_mysql import service_create_meeting_mysql

mysql_router = APIRouter(prefix="/v1/mysql/meetings", tags=["Meeting"])

@mysql_router.post("", description="meeting을 생성합니다.")
async def api_create_meeting_mysql() -> CreateMeetingResponse:
    meeting = await service_create_meeting_mysql()
    return CreateMeetingResponse(url_code=meeting.url_code)
```
[CI 환경에서 MySQL 설정]
#.github/workflows/ci.yml
```yaml
test:
  runs-on: ubuntu-22.04
  env:
    MYSQL_HOST: 127.0.0.1
    MYSQL_PORT: 3306
    MYSQL_USER: root
    MYSQL_PASSWORD: 1234
    MYSQL_DATABASE: when2meet_vod

  steps:
    - name: Set timezone to KST
      run: |
        sudo rm /etc/localtime
        sudo ln -s /usr/share/zoneinfo/Asia/Seoul /etc/localtime

    - name: Start Mysql
      run: |
        sudo systemctl start mysql
        mysql -e "use mysql; FLUSH PRIVILEGES; ALTER USER '${{ env.MYSQL_USER }}'@'localhost' IDENTIFIED BY '${{ env.MYSQL_PASSWORD }}';" -uroot -proot
        mysql -e 'CREATE DATABASE ${{ env.MYSQL_DATABASE }};' -u${{ env.MYSQL_USER }} -p${{ env.MYSQL_PASSWORD }}

    - name: Run tests
      run: |
        poetry run coverage run -m pytest .
        poetry run coverage report -m
```

| 구분          | 특징                      | 예시                               |
| ----------- | ----------------------- | -------------------------------- |
| **단위 테스트**  | 함수/서비스 단위 테스트           | `service_create_meeting_mysql()` |
| **통합 테스트**  | DB, 외부 API 포함           | MeetingModel insert 확인           |
| **E2E 테스트** | 실제 API 호출 & 사용자 시나리오 검증 | httpx로 `/v1/mysql/meetings` 호출   |
단위테스트 > 통합테스트 > E2E 테스트 순으로 많은 게 이상적.
하지만 최근엔 E2E 테스트 중심으로 가는 추세
(내부 구현 변경해도 테스트 영향 최소화)
API 중심으로 커버리지 확보 가능
