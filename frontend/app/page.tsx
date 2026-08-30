import { Dashboard } from "../components/dashboard";
export default async function Home({ searchParams }: { searchParams: Promise<{ dataset?: string }> }) {
  return <Dashboard initialDataset={(await searchParams).dataset ?? ""} />;
}
