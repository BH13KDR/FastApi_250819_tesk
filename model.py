from typing import Optional
from pydantic import BaseModel, Field

# 영화 등록 요청 모델
class MovieCreate(BaseModel):
    title: str = Field(..., min_length=1, example="Inception")
    playtime: int = Field(..., gt=0, example=148)  # 0보다 커야 함
    genre: str = Field(..., min_length=1, example="Sci-Fi")

# 영화 모델
class MovieModel(MovieCreate):
    id: int

    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "title": "Inception",
                "playtime": 148,
                "genre": "Sci-Fi"
            }
        }

# 영화 검색 Query 모델
class MovieSearchQuery(BaseModel):
    title: Optional[str] = Field(None, example="Inception")
    genre: Optional[str] = Field(None, example="Sci-Fi")
