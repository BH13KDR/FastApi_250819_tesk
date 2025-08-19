from fastapi import FastAPI, HTTPException, Path, Query, status
from typing import List
from models import MovieCreate, MovieModel, MovieSearchQuery

app = FastAPI(title="Movie API", description="영화 관리 API")

# 예시용 DB
movies_db: List[MovieModel] = []
next_id = 1


# 1. 영화 등록 API
@app.post("/movies", response_model=MovieModel, status_code=status.HTTP_201_CREATED)
def create_movie(movie: MovieCreate):
    global next_id
    new_movie = MovieModel(id=next_id, **movie.dict())
    movies_db.append(new_movie)
    next_id += 1
    return new_movie


# 2. 전체 영화 검색 및 리스트 조회 API
@app.get("/movies", response_model=List[MovieModel])
def list_movies(title: str | None = Query(None), genre: str | None = Query(None)):
    if title or genre:
        filtered = [
            m for m in movies_db
            if (title and title.lower() in m.title.lower())
            or (genre and genre.lower() in m.genre.lower())
        ]
        return filtered if filtered else movies_db
    return movies_db


# 3. 특정 영화 상세 조회 API
@app.get("/movies/{movie_id}", response_model=MovieModel)
def get_movie(movie_id: int = Path(..., ge=1)):
    movie = next((m for m in movies_db if m.id == movie_id), None)
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return movie


# 4. 특정 영화 정보 수정 API
@app.put("/movies/{movie_id}", response_model=MovieModel)
def update_movie(movie_id: int = Path(..., ge=1), updated: MovieCreate = None):
    movie = next((m for m in movies_db if m.id == movie_id), None)
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")

    movie.title = updated.title
    movie.playtime = updated.playtime
    movie.genre = updated.genre
    return movie


# 5. 특정 영화 정보 삭제 API
@app.delete("/movies/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movie(movie_id: int = Path(..., ge=1)):
    global movies_db
    movie = next((m for m in movies_db if m.id == movie_id), None)
    if not movie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    movies_db = [m for m in movies_db if m.id != movie_id]
    return None
