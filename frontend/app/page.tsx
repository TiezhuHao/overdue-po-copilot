"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Dashboard } from "../components/dashboard";
import { Loading, Shell } from "../components/ui";

function DashboardRoute() {
  return <Dashboard initialDataset={useSearchParams().get("dataset") ?? ""} />;
}

export default function Home() {
  return <Suspense fallback={<Shell><main><Loading /></main></Shell>}><DashboardRoute /></Suspense>;
}
