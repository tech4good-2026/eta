# ETA 프론트엔드

ETA_v2 디자인을 유지하면서 FastAPI 경로·안내 API와 카카오 장소 검색을 연결한 React/Vite 앱입니다.

## 실행

```bash
cp .env.example .env
npm install
npm run dev
```

- 프론트: `http://localhost:5173`
- 백엔드 기본값: `http://localhost:8000/api/v1`
- 데모 계정: `test@eta.com / password123`

`.env`의 `VITE_KAKAO_MAP_APP_KEY`에는 카카오 JavaScript 키를 넣고, 카카오 개발자 콘솔에서 `http://localhost:5173`과 실제 배포 도메인만 허용합니다. TMAP·서울 공공데이터 키는 프론트에 넣지 않습니다.

## 검증

```bash
npm test
npm run lint
npm run build
```

프론트는 모든 백엔드 요청에 `Bearer demo-token`을 붙입니다. 장소 검색은 카카오 브라우저 SDK가 담당하고, 경로 검색·안내·재탐색·완료는 FastAPI만 호출합니다.
