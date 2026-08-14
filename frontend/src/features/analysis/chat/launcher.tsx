export function ChatLauncher({
  disabled = false,
  loading = false,
  onOpen,
}: {
  disabled?: boolean;
  loading?: boolean;
  onOpen?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={disabled || loading}
      className="fixed right-5 bottom-5 z-40 min-h-14 rounded-2xl bg-blue-600 px-6 py-4 text-base font-semibold text-white shadow-xl disabled:cursor-not-allowed disabled:bg-zinc-300 sm:right-8 sm:bottom-8"
    >
      {loading ? "상담창을 준비하고 있어요…" : "AI 상담사에게 질문하기"}
    </button>
  );
}
