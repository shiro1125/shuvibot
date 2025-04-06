# Python 베이스 이미지
FROM python:3.11

# 작업 디렉토리 설정
WORKDIR /app

# requirements 설치 (없으면 무시됨)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt || true

# 코드 복사
COPY . .

# 실행
CMD ["python", "bot.py"]
