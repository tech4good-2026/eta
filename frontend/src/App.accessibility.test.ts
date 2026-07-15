import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("main map search entry", () => {
  it("uses a semantic button so keyboard and automation can activate search", () => {
    const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
    const section = source.match(
      /\{\/\* Float Search Entry Panel \*\/\}([\s\S]*?)\{origin &&/,
    )?.[1];

    expect(section).toBeDefined();
    expect(section).toContain('<button\n                  type="button"');
  });

  it("uses semantic buttons for Kakao place search results", () => {
    const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

    expect(source).toMatch(
      /\{placeResults\.map\(\(p\) => \(\s*<button\s+type="button"/,
    );
  });

  it("uses semantic buttons for route result cards", () => {
    const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

    expect(source).toMatch(
      /\{routes\.map\(\(route, rIdx\) => \{[\s\S]*?return \(\s*<button\s+type="button"/,
    );
  });
});

describe("default current location origin", () => {
  it("hides the location prompt as soon as location resolution starts", () => {
    const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

    expect(source).toContain('"PROMPT" | "REQUESTING" | "GRANTED" | "DENIED"');
    expect(source).toContain('setGeolocationStatus("REQUESTING")');
    expect(source).toContain('geolocationStatus === "PROMPT"');
  });

  it("resolves the current origin when a destination is selected without an origin", () => {
    const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

    expect(source).toContain("void requestCurrentOrigin(searchTarget)");
  });
});
