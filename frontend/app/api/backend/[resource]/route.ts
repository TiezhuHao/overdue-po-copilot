import { proxy } from "../../../../lib/proxy";
export const runtime = "nodejs";
export async function GET(request: Request, context: { params: Promise<{ resource: string }> }) {
  return proxy(request, (await context.params).resource);
}
export async function POST(request: Request, context: { params: Promise<{ resource: string }> }) {
  return proxy(request, (await context.params).resource);
}
