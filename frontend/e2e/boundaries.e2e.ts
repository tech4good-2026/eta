import { expect, test } from '@playwright/test';

test('실제 데모 API의 경로 결과와 합성 데이터 표시', async ({ page }, info) => {
  // 유료/키가 필요한 외부 장소 SDK만 대체한다. ETA API는 실제 로컬 서버를 호출한다.
  await page.route('https://**/*', route => route.abort());
  await page.addInitScript(() => {
    (window as any).kakao = { maps: { services: { Status: { OK: 'OK', ZERO_RESULT: 'ZERO' },
      Places: class { keywordSearch(query: string, callback: (...args: any[]) => void) {
        callback([{ id: query, place_name: query, address_name: '서울시 데모 위치', road_address_name: '',
          category_group_name: '지하철역', category_name: '교통', phone: '', place_url: '',
          x: query === '서울역' ? '126.9707' : '127.1001', y: query === '서울역' ? '37.5547' : '37.5133' }], 'OK');
      } } } } };
  });
  await page.goto('/');
  await page.getByPlaceholder('example@eta.com').fill('test@eta.com');
  await page.locator('input[type=password]').fill('password123');
  await page.getByRole('button', { name: '내 안전 속도로 로그인하기' }).click();
  await page.getByRole('button', { name: '어디로 안전하게 우회하여 이동할까요?' }).click();
  await page.getByPlaceholder('2자 이상의 장소명 또는 주소를 검색하세요...').fill('서울역');
  await page.getByRole('button', { name: /서울역 지하철역 서울시 데모 위치/ }).click();
  await page.getByRole('button', { name: '출발지로 지정' }).click();
  await page.getByRole('button', { name: '어디로 안전하게 우회하여 이동할까요?' }).click();
  await page.getByPlaceholder('2자 이상의 장소명 또는 주소를 검색하세요...').fill('잠실역');
  await page.getByRole('button', { name: /잠실역 지하철역 서울시 데모 위치/ }).click();
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/v1/routes/search'));
  await page.getByRole('button', { name: '목적지로 지정' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.dataMode).toBe('DEMO');
  expect(body.routes.length).toBeGreaterThan(0);
  await expect(page.getByText('합성 데이터 데모 · 실제 길 안내가 아닙니다.')).toBeVisible();
  await expect(page.locator('#view-route-search-screen')).toBeVisible();
  await expect(page.getByText('출발지 설정이 완료되었습니다. 남은 한 곳을 등록하세요.')).not.toBeVisible();
  await page.screenshot({ path: `artifacts/demo-${info.project.name}.png`, fullPage: true });
});
