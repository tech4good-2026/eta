# Kakao Map Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카카오 Developers 원본 앱을 비즈 앱으로 전환하고 개발용 테스트 앱의 JavaScript 키를 로컬 프론트엔드에 연결해 장소 검색과 지도 렌더링을 검증한다.

**Architecture:** 카카오 Developers의 `Tech4Good Navigation` 원본 앱에 등록용 아이콘을 추가하고 개인 개발자 비즈 앱으로 전환한다. 미배포 서비스는 원본 앱 심사에 필요한 실제 서비스 URL이 없으므로 테스트 앱 `Tech4Good Navigation-TEST`에서 카카오맵을 활성화한다. JavaScript 키는 Git에서 제외되는 `frontend/.env`에만 저장하며, React/Vite 앱은 기존 Kakao Maps SDK 로더와 Places 서비스를 그대로 사용한다.

**Tech Stack:** Kakao Developers, Kakao Maps JavaScript SDK, React 19, Vite 6, FastAPI, PNG 128×128px

## Global Constraints

- 앱 아이콘은 파란색·민트색의 지도 핀, 이동 경로, 시계 심볼을 사용한다.
- 특정 장애 유형이나 이동 보조기구, 텍스트, 상표, 워터마크를 포함하지 않는다.
- 최종 아이콘은 `assets/tech4good-kakao-icon.png`, 128×128px PNG, 250KB 이하로 저장한다.
- 카카오 JavaScript 키는 `frontend/.env`에만 저장하고 출력·커밋하지 않는다.
- 허용 도메인은 개발용 `http://localhost:5173`과 실제로 확인된 배포 도메인만 등록한다.
- 기존 프론트 레이아웃과 Tailwind 클래스는 변경하지 않는다.
- 개발용 카카오 앱은 테스트 앱 ID `1514932`를 사용하고, 원본 앱 ID `1514916`의 심사는 실제 배포 URL이 생긴 뒤 진행한다.

---

### Task 1: 카카오 등록용 아이콘 제작

**Files:**
- Create: `assets/tech4good-kakao-icon.png`
- Reference: `docs/superpowers/specs/2026-07-15-kakao-app-icon-design.md`

**Interfaces:**
- Consumes: 승인된 아이콘 디자인 명세
- Produces: 카카오 Developers 업로드 규격을 만족하는 PNG 파일

- [x] **Step 1: 아이콘 생성**

이미지 생성 도구에 다음 프롬프트를 사용한다.

```text
Use case: logo-brand
Asset type: Kakao Developers app icon
Primary request: an inclusive mobility navigation icon combining a map pin, a simple curved route, and a small clock
Style/medium: crisp flat vector-like illustration rendered as a square bitmap
Composition/framing: centered single symbol, generous padding, readable at 32px
Color palette: deep blue and mint on a clean light background
Constraints: no text, no letters, no wheelchair symbol, no person, no trademark, no watermark, no photographic texture
```

- [x] **Step 2: 프로젝트 자산으로 복사하고 128×128px로 변환**

생성 결과를 `assets/tech4good-kakao-icon-source.png`에 복사한 뒤 다음 명령을 실행한다.

```bash
mkdir -p assets
sips -z 128 128 assets/tech4good-kakao-icon-source.png \
  --out assets/tech4good-kakao-icon.png
rm assets/tech4good-kakao-icon-source.png
```

Expected: `assets/tech4good-kakao-icon.png` 생성.

- [x] **Step 3: 파일 규격 검증**

```bash
sips -g format -g pixelWidth -g pixelHeight assets/tech4good-kakao-icon.png
stat -f '%z' assets/tech4good-kakao-icon.png
```

Expected: `format: png`, `pixelWidth: 128`, `pixelHeight: 128`, 파일 크기 `256000`바이트 미만.

- [x] **Step 4: 아이콘 자산 커밋**

```bash
git add assets/tech4good-kakao-icon.png
git commit -m "assets: add Kakao app icon"
```

### Task 2: 비즈 앱 전환과 개발용 테스트 앱 활성화

**Files:**
- No repository file changes

**Interfaces:**
- Consumes: `assets/tech4good-kakao-icon.png`, Kakao app ID `1514916`
- Produces: 개인 개발자 비즈 앱 원본과 카카오맵 권한을 보유한 테스트 앱

- [x] **Step 1: 앱 아이콘 업로드**

Kakao Developers `앱 설정 > 앱 > 일반 > 앱 기본 정보 > 수정`에서 `assets/tech4good-kakao-icon.png`를 업로드하고 저장한다.

Expected: 앱 기본 정보 표에 새 아이콘 표시.

- [x] **Step 2: 개인 개발자 비즈 앱 전환**

`비즈니스 정보 > 비즈 앱 등록`에서 사업자 번호가 없는 개인 개발자 경로를 선택하고 본인인증과 카카오비즈니스 통합 서비스 약관 동의를 완료한다.

Expected: `이 앱은 비즈 앱입니다` 상태 표시. 본인인증 입력은 사용자가 브라우저에서 직접 완료한다.

- [x] **Step 3: 개발용 테스트 앱 생성 및 카카오맵 활성화**

원본 앱의 `테스트 앱 생성`에서 `Tech4Good Navigation-TEST`를 만들고, 테스트 앱의 `제품 설정 > 카카오맵 > 사용 설정`을 `ON`으로 변경한다.

Expected: 테스트 앱 ID `1514932`, 카카오맵 사용 설정 `ON`.

### Task 3: JavaScript 키와 Web 플랫폼 설정

**Files:**
- Create (ignored): `frontend/.env`
- Reference: `frontend/.env.example`

**Interfaces:**
- Consumes: 카카오맵이 활성화된 테스트 앱의 JavaScript 플랫폼 키
- Produces: Vite 런타임에서 로드 가능한 `VITE_KAKAO_MAP_APP_KEY`

- [x] **Step 1: Web 플랫폼과 도메인 등록**

테스트 앱 `1514932`의 `앱 설정 > 앱 > 플랫폼 키`에서 JavaScript 키를 선택하고 Web 플랫폼에 `http://localhost:5173`을 등록한다. 배포 도메인은 실제 URL이 결정되기 전에는 추가하지 않는다.

Expected: 허용 도메인 목록에 `http://localhost:5173` 표시.

- [x] **Step 2: 로컬 환경 파일 생성**

브라우저에서 JavaScript 키를 복사한 뒤 셸 출력 없이 `KAKAO_JS_KEY` 환경변수로 전달하고 다음 명령으로 `frontend/.env`를 만든다.

```bash
umask 077
printf 'VITE_API_BASE_URL=http://localhost:8000/api/v1\nVITE_KAKAO_MAP_APP_KEY=%s\n' \
  "$KAKAO_JS_KEY" > frontend/.env
unset KAKAO_JS_KEY
```

Expected: `git check-ignore frontend/.env` 성공, `git status --short`에 `frontend/.env` 미표시.

- [x] **Step 3: SDK 직접 확인**

```bash
set -a
source frontend/.env
set +a
curl -sS -o /dev/null -w '%{http_code}\n' \
  "https://dapi.kakao.com/v2/maps/sdk.js?appkey=${VITE_KAKAO_MAP_APP_KEY}&libraries=services&autoload=false"
```

Expected: HTTP `200`.

### Task 4: 프론트–백엔드 전체 흐름 검증

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/App.accessibility.test.ts`

**Interfaces:**
- Consumes: `frontend/.env`, `backend/.env`, FastAPI route APIs, Kakao Maps SDK
- Produces: 브라우저에서 검증된 로그인→장소 검색→대중교통 경로→재탐색→완료 흐름

- [x] **Step 1: 정적 테스트 실행**

```bash
cd backend && uv run pytest && uv run ruff check .
cd ../frontend && npm test && npm run lint && npm run build
```

Expected: 백엔드 44개 테스트, 프론트 16개 테스트, Ruff, TypeScript, Vite build 모두 통과.

- [x] **Step 2: 개발 서버 실행**

터미널 1:

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

터미널 2:

```bash
cd frontend
npm run dev
```

Expected: 백엔드 `http://127.0.0.1:8000/health` 200, 프론트 `http://localhost:5173` 응답.

- [x] **Step 3: 브라우저 사용자 흐름 확인**

1. `test@eta.com / password123`로 로그인한다.
2. 프로필 조회와 저장 요청이 200인지 확인한다.
3. 목적지 검색창에 `서울시청`을 입력하고 카카오 장소 결과가 표시되는지 확인한다.
4. 대중교통 탭에서 실제 TMAP 경로가 표시되는지 확인한다.
5. 경로 상세의 GeoJSON 선, ETA, 접근성 상태가 렌더링되는지 확인한다.
6. 가상 이탈 감지 후 재탐색을 승인하고 `routeRevision`이 증가하는지 확인한다.
7. 안내 완료 후 원본 위치 삭제 안내와 완료 API 응답을 확인한다.

Expected: 지도와 검색 결과 표시, `/api/v1/routes/search` 200, 안내 세션 `ACTIVE`, 재탐색 후 `routeRevision` 1→2, 완료 API 200.

- [x] **Step 4: 종료와 Git 상태 확인**

```bash
git status --short --branch
```

Expected: `frontend/.env`와 공급자 키가 Git 변경 목록에 없고, 의도한 소스·테스트·문서만 존재.

### Task 5: 배포 후 원본 앱 카카오맵 심사

- [ ] 실제 서비스 URL과 로그인 없이 확인 가능한 서비스 화면을 준비한다.
- [ ] 원본 앱의 비즈니스 정보 심사에 배포 URL과 서비스 화면을 제출한다.
- [ ] 비즈니스 정보 승인 후 원본 앱 카카오맵 권한을 신청하고 배포 키로 교체한다.

심사 추가 정보에는 다음 설명을 사용한다.

```text
Tech4Good 2026 해커톤에서 거동이 불편한 교통약자에게 개인 보행속도와 접근성 정보를 반영한 대중교통·도보 경로를 제공하는 웹 내비게이션입니다. 카카오맵 JavaScript SDK는 지도 표시와 목적지 장소 검색에만 사용합니다.
```
