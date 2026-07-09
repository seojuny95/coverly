import Link from "next/link";

export default function Home() {
  return (
    <main className="bg-background text-foreground flex min-h-screen items-center justify-center px-6 py-16">
      <section className="w-full max-w-2xl">
        <p className="mb-3 text-sm font-medium text-zinc-500">Coverly</p>
        <h1 className="text-4xl font-semibold tracking-normal text-zinc-950 sm:text-5xl">
          보험 보장을 근거 있게 읽는 앱
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-8 text-zinc-600">
          증권 업로드, 보장 구조화, 진단 리포트, 약관 기반 Q&A를 위한 기본
          골격을 준비했습니다.
        </p>
        <Link
          href="/upload"
          className="mt-8 inline-flex bg-zinc-950 px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-zinc-800"
        >
          증권 업로드
        </Link>
      </section>
    </main>
  );
}
