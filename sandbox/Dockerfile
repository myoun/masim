FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# 작업 디렉터리 설정
RUN adduser --disabled-password --gecos '' runner \
    && mkdir -p /sandbox \
    && chown runner:runner /sandbox

WORKDIR /sandbox

# 시스템 의존성 설치
USER root

# 타임존 설정
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

# Manim 기본 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libcairo2-dev \
    libpango1.0-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# TeX Live 기본 설치 및 Manim 필수 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-science \
    texlive-xetex \
    dvisvgm \
    cm-super \
    dvipng \
    && rm -rf /var/lib/apt/lists/*

# Manim 필수 LaTeX 패키지 (tlmgr로 추가 설치)
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-lang-chinese \
    texlive-plain-generic \
    && rm -rf /var/lib/apt/lists/*

# 원래 파일 복사
COPY pyproject.toml .
COPY uv.lock .
COPY .python-version .

# runner 사용자로 변경
USER runner

# Python 의존성 설치
RUN uv sync --no-cache

# 작업 디렉터리를 runner가 쓸 수 있도록 보장
WORKDIR /sandbox