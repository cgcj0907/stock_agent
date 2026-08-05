import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 本地开发：允许通过 127.0.0.1 访问（避免跨源拦截 dev 资源）
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
