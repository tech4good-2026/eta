# README 이미지와 구조도

- 촬영·검증일: 2026-10-02.
- 화면 조건: 실제 로컬 FastAPI의 DEMO 응답. frontend/e2e/boundaries.e2e.ts가 외부 장소 SDK만 테스트 대역으로 대체. 실제 지도·길찾기 정확도 미검증.
- `screens/demo-desktop.png`는 실제 브라우저 캡처입니다. 숫자·배지를 이미지 편집으로 바꾸지 않았습니다.
- `screens/demo-mobile.png`가 있으면 같은 흐름의 모바일 캡처입니다.
- `architecture/request-flow.svg`는 현재 구현의 핵심 판단을 설명하는 편집 가능한 원본입니다. 전체 인프라 배치도를 뜻하지 않습니다.
- 구조도의 색상·타이포그래피·레이아웃과 README 내 이미지 위치를 다른 포트폴리오 저장소와 맞췄습니다. 실제 서비스 화면의 기존 브랜드는 유지합니다.
- 대체 설명은 README의 이미지 alt와 그림 설명, SVG의 title·desc에 함께 있습니다.

자산 해시는 [manifest.json](manifest.json)에 기록합니다. 이미지 변경 시 실제 동작을 다시 캡처하고 해시도 갱신합니다. 링크·PNG 크기·SVG 검사는 `python3 scripts/check-readme.py`로 실행합니다.
