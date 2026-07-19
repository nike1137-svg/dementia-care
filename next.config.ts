import type { NextConfig } from "next";

// api-spec §0.1: 브라우저는 항상 /api/py/* 만 호출한다(same-origin, CORS 없음).
// 실제 백엔드 주소는 BACKEND_URL(.env.local / .env.example)에서만 읽는다 — 코드에 박지 않는다.
const BACKEND_URL = process.env.BACKEND_URL;

const nextConfig: NextConfig = {
  async rewrites() {
    if (!BACKEND_URL) {
      throw new Error("BACKEND_URL 환경변수가 없습니다 (.env.local 확인)");
    }
    return [
      { source: "/api/py/:path*", destination: `${BACKEND_URL}/:path*` },
    ];
  },
};

export default nextConfig;
