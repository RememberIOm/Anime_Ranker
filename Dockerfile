FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 데이터 저장소 디렉토리 생성 (Volume 마운트 포인트)
RUN mkdir -p /data

# 포트 노출 (Fly.io 기본값 8080)
EXPOSE 8080

# DB 경로 환경변수 설정 (Volume 경로)
ENV DB_PATH=/data/anime_rank.db

# 앱 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]