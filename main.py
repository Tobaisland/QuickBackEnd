from contextlib import asynccontextmanager
from urllib import response
from fastapi import FastAPI, Depends, HTTPException, Security, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
from pydantic import BaseModel, EmailStr, ConfigDict
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.future import select
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from config import settings
from loguru import logger

logger.add("logs/backend_{time}.log", rotation="1 day", retention="7 days", level="INFO")

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String, index=True)
    email = Column(String, unique=True, index=True)

class UserCreate(BaseModel):
    nama: str
    email: EmailStr

class UserResponse(BaseModel):
    id: int
    nama: str
    email: str

    model_config = ConfigDict(from_attributes=True)

def write_log_background(email: str):
    logger.info(f"Registrasi berhasil untuk user dengan email: {email}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="QuickBackend API",
    description="API Asinkron, Cepat, Terstruktur, dan Aman",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = settings.API_KEY
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Akses ditolak. API Key tidak valid."
        )
    return api_key

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

@app.get("/", tags=["Sistem"])
async def root():
    return {"message": "Server berjalan"}

@app.get("/health_check", tags=["Sistem"])
async def ping():
    return {"result": "healthy"}

@app.post("/users/", response_model=UserResponse, tags=["Users"])
@limiter.limit("5/minute")
async def create_user(request: Request, user: UserCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    result = await db.execute(select(User).filter(User.email == user.email))
    db_user = result.scalars().first()
    
    if db_user:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    
    new_user = User(nama=user.nama, email=user.email)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    background_tasks.add_task(write_log_background, user.email)
    return new_user

@app.get("/users/", response_model=list[UserResponse], tags=["Users"])
async def read_users(skip: int = 0, limit: int = 10, search: str = "", db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    query = select(User)
    if search:
        query = query.filter(User.nama.contains(search))
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def read_user(user_id: int, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    result = await db.execute(select(User).filter(User.id == user_id))
    db_user = result.scalars().first()
    
    if db_user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return db_user

@app.put("/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def update_user(user_id: int, user: UserCreate, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    result = await db.execute(select(User).filter(User.id == user_id))
    db_user = result.scalars().first()
    
    if db_user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    
    db_user.nama = user.nama
    db_user.email = user.email
    await db.commit()
    await db.refresh(db_user)
    return db_user

@app.delete("/users/{user_id}", tags=["Users"])
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), api_key: str = Depends(get_api_key)):
    result = await db.execute(select(User).filter(User.id == user_id))
    db_user = result.scalars().first()
    
    if db_user is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    
    await db.delete(db_user)
    await db.commit()
    return {"detail": "User dihapus"}