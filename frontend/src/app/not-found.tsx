import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f5f7] px-5 py-12 text-zinc-950">
      <section className="w-full max-w-md rounded-[8px] border border-zinc-200 bg-white px-5 py-6 shadow-[0_16px_60px_rgba(0,0,0,0.06)] sm:px-7 sm:py-7">
        <p className="text-sm font-semibold text-zinc-950">Coverly</p>
        <h1 className="mt-5 text-2xl leading-8 font-semibold tracking-normal">
          페이지를 찾을 수 없습니다.
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          주소가 바뀌었거나 삭제된 페이지일 수 있습니다.
        </p>
        <Link
          href="/upload"
          className="mt-6 inline-flex rounded-[8px] bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2 focus:outline-none"
        >
          업로드로 이동
        </Link>
      </section>
    </main>
  );
}
