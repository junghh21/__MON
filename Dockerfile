FROM alpine:latest

# git, python3, pip 설치
RUN apk update && apk add --no-cache \
    git \
    python3 \
    py3-pip

# 기본 작업 디렉토리 설정
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

#CMD ["python3"]
