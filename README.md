# Anime Ranker (Elo Rating System)

**Anime Ranker**는 애니메이션 1:1 대결 투표를 통해 실시간으로 순위를 산정하는 웹 애플리케이션입니다.
체스 등에서 사용되는 **Elo Rating 알고리즘**을 기반으로 하며, 스토리, 작화, OST 등 6가지 세부 항목에 대한 정밀한 평가 시스템을 갖추고 있습니다.

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-Async-red?style=flat-square)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-Integration-38B2AC?style=flat-square&logo=tailwind-css)

---

## ✨ 주요 기능 (Key Features)

### 1. ⚔️ Battle Arena (투표 시스템)
- **1vs1 대결**: 무작위 또는 알고리즘에 의해 선정된 두 애니메이션 중 하나를 선택합니다.
- **Smart Matchmaking**: 비슷한 점수대의 '라이벌'을 매칭하여 대결의 긴장감을 높입니다 (80% 확률).
- **Focus Mode**: 특정 애니메이션을 집중적으로 평가할 수 있는 모드를 지원합니다.
- **동적 카테고리**: 스토리, 작화, OST, 성우, 캐릭터, 종합 재미 중 랜덤한 주제로 대결합니다.

### 2. 🏆 Ranking Board (순위표)
- **실시간 랭킹**: 투표 즉시 Elo 점수가 계산되어 순위에 반영됩니다.
- **다차원 분석**: 종합 점수 외 각 카테고리별(스토리, 작화 등) 순위를 별도로 확인할 수 있습니다.
- **시각화**: Chart.js를 활용하여 현재 점수 분포(Distribution)를 그래프로 보여줍니다.

### 3. ⚙️ Management (관리자 페이지)
- **데이터 관리**: 애니메이션 추가, 수정, 삭제가 가능합니다.
- **CSV 초기화**: `animation.csv` 파일이 존재할 경우 서버 시작 시 자동으로 데이터를 로드합니다.
- **보안**: HTTP Basic Auth를 통해 관리자 페이지 접근을 제어합니다.

### 4. 🎨 UI/UX
- **반응형 디자인**: TailwindCSS를 사용하여 모바일과 데스크톱 모두에 최적화되었습니다.
- **Dark Mode**: 시스템 설정 또는 토글 버튼을 통해 다크 모드를 완벽하게 지원합니다.
- **Interactive UI**: 플로팅 애니메이션, 점수 카운팅 효과 등 동적인 인터랙션을 제공합니다.

---

## 🛠 기술 스택 (Tech Stack)

- **Backend**: Python 3.10+, FastAPI
- **Database**: SQLite, SQLAlchemy 2.0 (Async/Await), Aiosqlite
- **Frontend**: Jinja2 Templates, TailwindCSS (CDN), Chart.js
- **Deployment**: Fly.io (Docker environment compatible)

---

## 🚀 설치 및 실행 (Installation)

### 1. 클론 및 가상환경 설정
```bash
git clone https://github.com/your-username/anime-ranker.git
cd anime-ranker

python -m venv venv
# Windows
source venv/Scripts/activate
# Mac/Linux
source venv/bin/activate
```

### 2. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정 (.env)
프로젝트 루트에 `.env` 파일을 생성하거나 `config.py`의 기본값을 수정합니다.
```ini
DB_PATH=./anime_rank.db
AUTH_USERNAME=admin
AUTH_PASSWORD=password
```

### 4. 서버 실행
```bash
uvicorn main:app --reload
```
브라우저에서 `http://localhost:8000`으로 접속합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
.
├── main.py              # 앱 진입점 (App Entrypoint & Auth)
├── config.py            # 설정 및 환경변수 관리 (Pydantic)
├── database.py          # 비동기 DB 엔진 및 세션 설정
├── models.py            # SQLAlchemy ORM 모델 정의
├── schemas.py           # Pydantic 데이터 검증 스키마
├── services.py          # 비즈니스 로직 (Elo 계산, 매치메이킹, 정규화)
├── routers/             # API 라우터 모듈
│   ├── battle.py        # 대결 및 투표 처리
│   ├── ranking.py       # 순위 조회 및 차트 데이터
│   └── manage.py        # 데이터 CRUD (관리자)
├── templates/           # Jinja2 HTML 템플릿
│   ├── base.html        # 레이아웃 및 공통 스크립트
│   ├── index.html       # 메인 페이지
│   ├── battle.html      # 대결 페이지
│   ├── ranking.html     # 랭킹 페이지
│   └── manage.html      # 관리 페이지
├── requirements.txt     # 의존성 목록
└── fly.toml             # Fly.io 배포 설정
```

---

## 🧠 알고리즘 상세 (Algorithm Logic)

### Elo Rating Configuration (`config.py`)
이 프로젝트는 단순 승패 기록이 아닌, **상대방의 점수에 따른 기대 승률**을 기반으로 점수를 변동시킵니다.

1.  **Dynamic K-Factor**:
    *   초기 진입 시 (`K=60`): 빠른 제자리 찾기를 위해 변동폭이 큽니다.
    *   안정화 후 (`K=24`): 많은 대결을 치른 후에는 점수 변동이 안정화됩니다.
2.  **Inflation Control**:
    *   `normalize_scores_task` 백그라운드 작업을 통해 전체 평균 점수가 1200점에서 크게 벗어나지 않도록 미세 조정하여 점수 인플레이션을 방지합니다.

### Smart Matchmaking (`services.py`)
*   **Rival Match (80%)**: 현재 애니메이션의 점수 기준 `±300`점 내의 상대를 우선 매칭하여 대결의 의미를 강화합니다.
*   **Random Match (20%)**: 랭킹 고착화를 방지하기 위해 가끔 완전 무작위 매칭을 수행합니다.

---

## ☁️ 배포 (Deployment)

이 프로젝트는 **Fly.io** 배포에 최적화되어 있습니다.

1. `flyctl` 설치 및 로그인.
2. 앱 생성: `fly launch`
3. 배포: `fly deploy`

*주의: `fly.toml`에 정의된 대로 `/data` 경로에 볼륨을 마운트하여 DB 영속성을 보장해야 합니다.*