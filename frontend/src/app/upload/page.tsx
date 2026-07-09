import { UploadForm } from "@/features/policy-upload/upload-form";

export default function UploadPage() {
  return (
    <main className="flex min-h-screen flex-col bg-white px-5 py-6 text-[#111827] sm:px-6">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between">
        <p className="text-sm font-semibold text-[#111827]">Coverly</p>
        <p className="text-sm text-[#111827]/70">보험증권 올리기</p>
      </header>

      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center py-12">
        <section className="mx-auto w-full max-w-2xl text-center">
          <h1 className="text-4xl leading-12 font-semibold tracking-normal text-[#111827] sm:text-5xl sm:leading-14">
            내 보험을 한눈에 정리해요
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-[#111827]/70">
            보험증권 PDF를 올리면 흩어진 보험 정보를 보기 쉽게 정리해드려요.
          </p>
        </section>

        <div className="mx-auto mt-10 w-full max-w-2xl">
          <UploadForm />
        </div>
      </div>
    </main>
  );
}
