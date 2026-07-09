import Link from "next/link";

export default function Home() {
  return (
    <main className="bg-background text-foreground flex min-h-screen items-center justify-center px-6 py-16">
      <section className="w-full max-w-2xl">
        <p className="mb-3 text-sm font-medium text-zinc-500">Coverly</p>
        <h1 className="text-4xl font-semibold tracking-normal text-zinc-950 sm:text-5xl">
          내 보험을 근거 있게 정리해요
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-8 text-zinc-600">
          보험증권 PDF를 올리면 흩어진 보험 정보를 보기 쉽게 정리해드려요.
        </p>
        <Link
          href="/upload"
          className="mt-8 inline-flex bg-zinc-950 px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-zinc-800"
        >
          보험증권 올리기
        </Link>
      </section>
    </main>
  );
}
