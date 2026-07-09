import { UploadForm } from "@/features/policy-upload/upload-form";

export default function UploadPage() {
  return (
    <main className="flex min-h-screen flex-col bg-white px-5 py-6 text-[#111827] sm:px-6">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between">
        <p className="text-sm font-semibold text-[#111827]">Coverly</p>
        <p className="text-sm text-[#111827]/70">증권 업로드</p>
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-1 items-center justify-center py-12">
        <UploadForm />
      </div>
    </main>
  );
}
