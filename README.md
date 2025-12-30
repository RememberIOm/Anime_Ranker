# ⚔️ Anime Battle Ranker

**Anime Battle Ranker**는 Elo Rating 시스템을 기반으로 애니메이션의 서열을 정하는 웹 애플리케이션입니다.  
사용자는 두 애니메이션 간의 1:1 대결(Battle)을 통해 투표하며, 결과는 실시간으로 랭킹에 반영됩니다.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-Red?style=flat-square)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)

---

## ✨ 주요 기능

- **1:1 배틀 시스템**: 무작위 매칭 또는 특정 애니메이션 집중 평가(배치고사) 모드 지원
- **Elo Rating 랭킹**: 스토리, 작화, OST 등 6가지 세부 항목별 점수 산정 및 종합 랭킹 제공
- **데이터 시각화**: 랭킹 페이지 내 점수 분포도 그래프 (Chart.js)
- **관리자 기능**: 애니메이션 추가, 수정, 삭제 기능
- **보안**: 전역 HTTP Basic Authentication 적용 (Timing Attack 방지)

---

## 🛠️ 설치 및 실행 가이드

이 프로젝트는 Python 3.10 이상 환경에서 실행하는 것을 권장합니다.

### 1. 프로젝트 클론 및 이동
```bash
git clone https://github.com/your-username/anime-ranker.git
cd anime-ranker
```

### 2. 가상환경 생성 및 활성화
가상환경을 사용하면 의존성 충돌을 방지할 수 있습니다.

**Windows (PowerShell)**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Mac / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. 패키지 설치
`requirements.txt`에 명시된 필수 라이브러리를 설치합니다.
```bash
pip install -r requirements.txt
```

---

## 🔐 환경 변수 설정 (보안)

이 앱은 모든 접근에 대해 **로그인**을 요구합니다.  
환경 변수를 설정하지 않으면 아래 **기본값**이 적용됩니다.

| 변수명 | 설명 | 기본값 (Default) |
| :--- | :--- | :--- |
| `AUTH_USERNAME` | 로그인 ID | `admin` |
| `AUTH_PASSWORD` | 로그인 비밀번호 | `password` |
| `DB_PATH` | SQLite DB 파일 경로 | `./anime_rank.db` |

**보안 설정 예시 (Linux/Mac)**
```bash
export AUTH_USERNAME="myuser"
export AUTH_PASSWORD="mypassword"
```
**보안 설정 예시 (Windows PowerShell)**
```powershell
$env:AUTH_USERNAME="myuser"
$env:AUTH_PASSWORD="mypassword"
```

---

## 🚀 서버 실행

`uvicorn`을 사용하여 로컬 개발 서버를 실행합니다.

```bash
uvicorn main:app --reload
```
- `--reload`: 코드가 변경되면 서버를 자동으로 재시작합니다 (개발용).

실행 후 브라우저에서 아래 주소로 접속하세요:
👉 **http://localhost:8000**

> **초기 로그인**: 설정한 환경 변수 혹은 기본값(`admin` / `password`)을 입력하세요.

---

## 📂 프로젝트 구조

```text
📦 anime-ranker
 ├── 📂 templates           # HTML 템플릿 (Jinja2)
 │    ├── battle.html       # 대결 페이지
 │    ├── index.html        # 메인 홈
 │    ├── manage.html       # 관리자 페이지
 │    └── ranking.html      # 랭킹 및 차트
 ├── database.py            # DB 연결 및 세션 설정 (Async)
 ├── main.py                # FastAPI 앱 엔트리포인트 & 라우터
 ├── models.py              # SQLAlchemy 모델 정의
 ├── rating.py              # Elo Rating 알고리즘 로직
 ├── requirements.txt       # 의존성 목록
 └── animation.csv          # (옵션) 초기 데이터 시딩용 파일
```

## 💾 초기 데이터 로드 (선택 사항)

앱 최초 실행 시 DB가 비어있다면, 프로젝트 루트 경로에 `animation.csv` 파일이 있을 경우 자동으로 데이터를 로드합니다.  
CSV 형식은 다음과 같아야 합니다:

```csv
이름,순위,총점
귀멸의 칼날,1,9.5
진격의 거인,2,9.8
...
```