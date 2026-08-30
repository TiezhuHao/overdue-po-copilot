import { Detail } from "../../../components/detail";
export default async function Page({ params, searchParams }: { params: Promise<{ scheduleId: string }>; searchParams: Promise<{ dataset?: string }> }) {
  const id = (await params).scheduleId, dataset = (await searchParams).dataset ?? "";
  return <Detail key={`${dataset}:${id}`} scheduleId={id} datasetId={dataset} />;
}
