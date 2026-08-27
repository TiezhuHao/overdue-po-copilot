import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Overdue PO Copilot",
  description: "Supply Chain Intelligence Platform"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
