import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Overdue PO Copilot",
  description: "超期采购订单智能诊断与决策系统 · 基于确定性证据的只读采购助手"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
