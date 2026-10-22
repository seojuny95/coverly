export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET() {
  console.info("[runtime]", JSON.stringify({ node: process.version }));
  return new Response(null, { status: 204 });
}
