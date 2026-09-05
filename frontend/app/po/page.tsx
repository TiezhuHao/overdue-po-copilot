"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Detail } from "../../components/detail";
import { Loading, Shell } from "../../components/ui";

function DetailRoute() {
  const search = useSearchParams();
  const scheduleId = search.get("schedule") ?? "";
  const datasetId = search.get("dataset") ?? "";
  return <Detail key={`${datasetId}:${scheduleId}`} scheduleId={scheduleId} datasetId={datasetId} />;
}

export default function Page() {
  return <Suspense fallback={<Shell detail><main><Loading text="正在定位订单身份与业务快照…" /></main></Shell>}><DetailRoute /></Suspense>;
}
