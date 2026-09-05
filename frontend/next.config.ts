import type { NextConfig } from "next";

const portfolioDemo = process.env.NEXT_PUBLIC_PORTFOLIO_DEMO === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const systemA = (process.env.SYSTEM_A_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
const systemB = (process.env.SYSTEM_B_API_BASE_URL ?? "http://127.0.0.1:8100/api/v1").replace(/\/$/, "");

const nextConfig: NextConfig = portfolioDemo
  ? { output: "export", trailingSlash: true, ...(basePath ? { basePath, assetPrefix: basePath } : {}) }
  : {
      async rewrites() {
        return [
          { source: "/api/backend/datasets", destination: `${systemA}/datasets` },
          { source: "/api/backend/orders", destination: `${systemA}/reports/overdue-pos` },
          { source: "/api/backend/copilot", destination: `${systemB}/copilot/query` },
        ];
      },
    };

export default nextConfig;
