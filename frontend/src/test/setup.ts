import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Her testten sonra çizilen bileşenleri temizle
afterEach(() => cleanup());
