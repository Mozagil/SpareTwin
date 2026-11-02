import { describe, expect, it } from "vitest";

// useEffect(() => ifade, ...) biçimi, ifade bir değer döndürürse sayfayı çökertir.
// Örnek: yeni tarayıcılarda window.scrollTo() bir Promise döndürür. Her zaman süslü parantez kullanılmalı.
const sources = import.meta.glob<string>(["../**/*.ts", "../**/*.tsx", "!../**/*.test.*"], {
  query: "?raw",
  import: "default",
  eager: true,
});

describe("useEffect kuralı", () => {
  it("kaynak dosyalar okunabiliyor", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(10);
  });

  it("useEffect gövdesi her zaman süslü parantezli olmalı", () => {
    const bad = Object.entries(sources).flatMap(([file, text]) =>
      text
        .split("\n")
        .map((line, i) => ({ file, n: i + 1, line }))
        .filter(({ line }) => /useEffect\(\s*\(\)\s*=>\s*[^{\s]/.test(line))
        .map(({ file, n, line }) => `${file}:${n}: ${line.trim()}`),
    );
    expect(bad).toEqual([]);
  });
});
