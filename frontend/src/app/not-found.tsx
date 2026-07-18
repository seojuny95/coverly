import Link from "next/link";
import { PixelEyebrow } from "@/shared/components/eyebrow";
import { CoverlyLogo } from "@/shared/components/logo";
import { Button } from "@/shared/components/ui/button";

export default function NotFound() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-white px-5 py-12 text-zinc-950">
      <CoverlyLogo className="absolute top-6 left-6" />
      <section className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white px-6 py-8 shadow-[10px_10px_0_#e8edff] sm:px-8">
        <PixelEyebrow>PAGE NOT FOUND</PixelEyebrow>
        <h1 className="mt-5 text-2xl leading-8 font-semibold tracking-[-0.04em]">
          이 페이지를 찾지 못했어요.
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          주소가 바뀌었거나 페이지가 없어졌을 수 있어요.
        </p>
        <Button asChild className="mt-6">
          <Link href="/upload">보험증권 올리기</Link>
        </Button>
      </section>
    </main>
  );
}
