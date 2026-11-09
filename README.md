QuickBackEnd

QuickBackEnd adalah proyek backend Python yang dibangun menggunakan kerangka kerja FastAPI, ORM SQLAlchemy, dan Alembic untuk migrasi database. Proyek ini mencakup konfigurasi Docker untuk kebutuhan deployment.

Persyaratan
Python 3.x

Git

Docker & Docker Compose (Opsional)

git clone https://github.com/Tobaisland/QuickBackEnd.git

cd QuickBackEnd

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt

alembic upgrade head

uvicorn main:app --reload

docker-compose up -d --build
