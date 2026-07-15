# Default Current Origin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 목적지만 선택한 사용자의 현재 GPS 위치를 자동 출발지로 사용하고, 위치 안내창을 선택 즉시 닫는다.

**Architecture:** 브라우저 Geolocation API를 Promise 기반 유틸리티로 격리하고 `App`은 위치 요청 상태와 화면 전환만 관리한다. 기존 `handleQueryRoutes`를 재사용하며 백엔드 API 계약과 화면 디자인은 변경하지 않는다.

**Tech Stack:** React 19, TypeScript 5.8, Vite 6, Vitest 3

## Global Constraints

- 초기 서울역 좌표는 지도 중심 표시용으로만 사용한다.
- 실제 위치 확인에 성공한 경우에만 `나의 현위치 (GPS)`를 출발지로 만든다.
- 위치 실패 시 경로 API를 호출하지 않고 출발지 검색 화면으로 이동한다.
- 위치 안내창은 `PROMPT` 상태에서만 표시한다.

---

### Task 1: 현재 위치 유틸리티

**Files:**
- Create: `frontend/src/utils/currentLocation.ts`
- Create: `frontend/src/utils/currentLocation.test.ts`

**Interfaces:**
- Produces: `getCurrentCoordinates(geolocation): Promise<{ lat: number; lng: number }>`
- Produces: `createCurrentLocationPlace(coords): Place`

- [ ] **Step 1: 실패하는 유틸리티 테스트 작성**

```ts
it("converts a successful browser position into app coordinates", async () => {
  const geolocation = {
    getCurrentPosition(success: PositionCallback) {
      success({ coords: { latitude: 37.5, longitude: 127 } } as GeolocationPosition);
    },
  } as Geolocation;

  await expect(getCurrentCoordinates(geolocation)).resolves.toEqual({ lat: 37.5, lng: 127 });
});

it("creates the current GPS place used as a route origin", () => {
  expect(createCurrentLocationPlace({ lat: 37.5, lng: 127 })).toMatchObject({
    id: "current-gps",
    name: "나의 현위치 (GPS)",
    lat: 37.5,
    lng: 127,
  });
});
```

- [ ] **Step 2: 테스트가 모듈 부재로 실패하는지 확인**

Run: `cd frontend && npm test -- src/utils/currentLocation.test.ts`
Expected: FAIL because `./currentLocation` does not exist.

- [ ] **Step 3: 최소 유틸리티 구현**

```ts
export function getCurrentCoordinates(geolocation: Geolocation | undefined): Promise<Coordinates> {
  if (!geolocation) return Promise.reject(new Error("GEOLOCATION_UNAVAILABLE"));
  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      reject,
    );
  });
}

export function createCurrentLocationPlace(coords: Coordinates): Place {
  return {
    id: "current-gps",
    name: "나의 현위치 (GPS)",
    addr: "GPS로 수신한 현재 실시간 좌표",
    tag: "현재 수신지점",
    lat: coords.lat,
    lng: coords.lng,
    category: "현위치",
    phone: "없음",
    placeUrl: "",
  };
}
```

- [ ] **Step 4: 유틸리티 테스트 통과 확인**

Run: `cd frontend && npm test -- src/utils/currentLocation.test.ts`
Expected: PASS.

### Task 2: 목적지 선택과 위치 안내창 연결

**Files:**
- Modify: `frontend/src/App.tsx:40-290`
- Modify: `frontend/src/App.tsx:500-550`
- Modify: `frontend/src/App.accessibility.test.ts`

**Interfaces:**
- Consumes: `getCurrentCoordinates`, `createCurrentLocationPlace`
- Produces: `PROMPT | REQUESTING | GRANTED | DENIED` 위치 상태와 목적지 선택 시 자동 경로 조회 흐름

- [ ] **Step 1: 실패하는 통합 소스 계약 테스트 작성**

```ts
it("hides the location prompt as soon as location resolution starts", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  expect(source).toContain('setGeolocationStatus("REQUESTING")');
  expect(source).toContain('geolocationStatus === "PROMPT"');
});

it("resolves the current origin when a destination is selected without an origin", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  expect(source).toContain("requestCurrentOrigin(searchTarget)");
});
```

- [ ] **Step 2: 테스트가 현재 동작에서 실패하는지 확인**

Run: `cd frontend && npm test -- src/App.accessibility.test.ts`
Expected: FAIL because `REQUESTING` and `requestCurrentOrigin(searchTarget)` are absent.

- [ ] **Step 3: 위치 요청과 목적지 자동 경로 흐름 구현**

```ts
type GeolocationStatus = "PROMPT" | "REQUESTING" | "GRANTED" | "DENIED";

const requestCurrentOrigin = async (routeDestination?: Place) => {
  if (locationRequestInFlightRef.current) return;
  locationRequestInFlightRef.current = true;
  setGeolocationStatus("REQUESTING");
  try {
    const coords = await getCurrentCoordinates(navigator.geolocation);
    const currentOrigin = createCurrentLocationPlace(coords);
    setCurrentCoords(coords);
    setOrigin(currentOrigin);
    setGeolocationStatus("GRANTED");
    if (routeDestination) await handleQueryRoutes(mode, currentOrigin, routeDestination);
  } catch {
    setGeolocationStatus("DENIED");
    setScreen("search");
    showToast("현재 위치를 확인할 수 없습니다. 출발지를 직접 검색해 주세요.");
  } finally {
    locationRequestInFlightRef.current = false;
  }
};
```

목적지 선택 시 `origin`이 없으면 목적지를 저장한 뒤 `void requestCurrentOrigin(searchTarget)`을 호출한다. 위치 안내창 조건은 `geolocationStatus === "PROMPT"`로 변경하고, `내 위치 자동 동의` 버튼은 `void requestCurrentOrigin()`을 호출한다.

- [ ] **Step 4: 프론트 전체 테스트와 빌드 확인**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`
Expected: all tests pass, TypeScript reports no errors, Vite build succeeds.

- [ ] **Step 5: 브라우저에서 두 사용자 흐름 확인**

1. 메인 화면에서 `내 위치 자동 동의` 클릭 즉시 안내창이 사라지는지 확인한다.
2. 출발지 없이 목적지를 선택하고 위치 확인 성공 시 경로 화면으로 이동하는지 확인한다.
3. 위치 실패 시 출발지 검색 화면과 실패 안내가 표시되는지 확인한다.

- [ ] **Step 6: 구현 커밋**

```bash
git add frontend/src/App.tsx frontend/src/App.accessibility.test.ts \
  frontend/src/utils/currentLocation.ts frontend/src/utils/currentLocation.test.ts
git commit -m "feat: use current location as default route origin"
```
