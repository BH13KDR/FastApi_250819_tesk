MySQL 기반 참가자 및 날짜 관리 기능 정리

[참가자 생성 및 날짜 초기화]

새로운 참가자를 생성하면 해당 미팅 기간(start_date ~ end_date) 동안의 날짜 row들을 자동으로 생성.
각 날짜별 상태에 따라
enabled: 참석 여부 (기본값 True)
starred: 별표 여부 (기본값 False)

[데이터 모델]

app/tortoise_models/participant.py
```python
class ParticipantModel(BaseModel, Model):
    meeting: fields.ForeignKeyRelation[MeetingModel] = fields.ForeignKeyField(
        "models.MeetingModel", related_name="participants", db_constraint=False
    )
    name = fields.CharField(max_length=100)

    @classmethod
    async def create_participant(cls, meeting_id: int, name: str):
        return await cls.create(meeting_id=meeting_id, name=name)
```



app/tortoise_models/participant_date.py
```python
class ParticipantDateModel(BaseModel, Model):
    participant: fields.ForeignKeyRelation[ParticipantModel] = fields.ForeignKeyField(
        "models.ParticipantModel", related_name="participant_dates", db_constraint=False
    )
    date = fields.DateField()
    enabled = fields.BooleanField(default=True)
    starred = fields.BooleanField(default=False)

    @classmethod
    async def bulk_create_participant_dates(cls, participant_id: int, dates: list[date]) -> None:
        await cls.bulk_create(
            [ParticipantDateModel(participant_id=participant_id, date=date) for date in dates]
        )
```        

| 메서드      | 동작        | 비고                           |
| -------- | --------- | ---------------------------- |
| `on`     | 날짜 참석 활성화 | enabled=True                 |
| `off`    | 날짜 참석 비활성화| enabled=False, starred=False |
| `star`   | 별표 표시     | starred=True, enabled=True   |
| `unstar` | 별표 해제     | starred=False                |

[쿼리 구현]

class ParticipantDateModel(BaseModel, Model):
```python

    @classmethod
    async def on(cls, participant_date_id: int):
        await cls.filter(id=participant_date_id).update(enabled=True)

    @classmethod
    async def off(cls, participant_date_id: int):
        await cls.filter(id=participant_date_id).update(enabled=False, starred=False)

    @classmethod
    async def star(cls, participant_date_id: int):
        await cls.filter(id=participant_date_id).update(enabled=True, starred=True)

    @classmethod
    async def unstar(cls, participant_date_id: int):
        await cls.filter(id=participant_date_id).update(starred=False)
```

[서비스 계층]

app/services/participant_date_service_mysql.py
```python
from app.tortoise_models.participant_date import ParticipantDateModel

async def service_turn_on_participant_date_mysql(participant_date_id: int):
    await ParticipantDateModel.on(participant_date_id)

async def service_turn_off_participant_date_mysql(participant_date_id: int):
    await ParticipantDateModel.off(participant_date_id)

async def service_star_participant_date_mysql(participant_date_id: int):
    await ParticipantDateModel.star(participant_date_id)

async def service_unstar_participant_date_mysql(participant_date_id: int):
    await ParticipantDateModel.unstar(participant_date_id)
```

[라우터 계층]
```python
app/apis/v1/participant_date_router.py

@mysql_router.patch("/on")
async def api_turn_on_date_mysql(request: TurnOnOffStarParticipantDateRequestMysql) -> GetMeetingResponse:
    await service_turn_on_participant_date_mysql(request.participant_date_id)

@mysql_router.patch("/off")
async def api_turn_off_date_mysql(request: TurnOnOffStarParticipantDateRequestMysql) -> GetMeetingResponse:
    await service_turn_off_participant_date_mysql(request.participant_date_id)

@mysql_router.patch("/star")
async def api_star_date_mysql(request: TurnOnOffStarParticipantDateRequestMysql) -> GetMeetingResponse:
    await service_star_participant_date_mysql(request.participant_date_id)

@mysql_router.patch("/unstar")
async def api_unstar_date_mysql(request: TurnOnOffStarParticipantDateRequestMysql) -> GetMeetingResponse:
    await service_unstar_participant_date_mysql(request.participant_date_id)
```

[참가자 삭제 기능]
참가자 삭제 시 연결된 모든 participant_dates도 함께 삭제.
단, meeting 자체는 삭제되면 안 됨.

[쿼리 구현]
```python
app/tortoise_models/participant.py

@classmethod
async def delete_by_id(cls, participant_id: int) -> int:
    return await cls.filter(id=participant_id).delete()


app/tortoise_models/participant_date.py

@classmethod
async def delete_by_participant_id(cls, participant_id: int) -> int:
    return await cls.filter(participant_id=participant_id).delete()
```
[서비스 구현]

app/services/participant_service_mysql.py
```python
import asyncio
from app.tortoise_models.participant import ParticipantModel
from app.tortoise_models.participant_date import ParticipantDateModel

async def service_delete_participant_mysql(participant_id: int) -> int:
    deleted_participant_count, _ = await asyncio.gather(
        ParticipantModel.delete_by_id(participant_id),
        ParticipantDateModel.delete_by_participant_id(participant_id),
    )
    return deleted_participant_count
```

[라우터 구현]

```python
@mysql_router.delete("/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_participant_mysql(participant_id: int):
    deleted_count = await service_delete_participant_mysql(participant_id)
    if not deleted_count:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"participant with id: {participant_id} not found",
        )
```

[테스트 전략]

1. 참가자 생성 및 날짜 자동 생성
2. 날짜 On / Off / Star / Unstar
3. 참가자 삭제 및 연결된 날짜 삭제
4. Meeting 미존재 시 예외 처리

[대표 테스트 예시]

```python
async def test_turn_off_participant_date(self):
    response = await client.patch(
        "/v1/mysql/participant_dates/off",
        json={"participant_date_id": dates[0]["id"], "meeting_url_code": url_code},
    )
    self.assertEqual(response.status_code, HTTP_200_OK)
    participant_date = await ParticipantDateModel.filter(id=dates[0]["id"]).get()
    self.assertFalse(participant_date.enabled)

async def test_delete_participant(self):
    response = await client.delete(f"/v1/mysql/participants/{participant_id}")
    self.assertEqual(response.status_code, HTTP_204_NO_CONTENT)
    participant = await ParticipantModel.filter(id=participant_id).get_or_none()
    self.assertIsNone(participant)
    participant_dates = await ParticipantDateModel.filter(participant_id=participant_id).all()
    self.assertEqual(len(participant_dates), 0)
```

[핵심 정리]

날짜 상태 관리 → enabled, starred 필드로 제어.

쿼리 최적화 → 날짜 row는 미리 bulk insert.

삭제 처리 → Foreign Key db_constraint=False → dates 자동 삭제 안 됨 → 서비스 레벨에서 명시적 삭제 필요.

성능 최적화 → asyncio.gather()로 병렬 삭제 처리.

테스트 전략 :
    - 정상 동작 검증
    - 예외 케이스(404) 검증
    - DB 상태 검증