type ChatSource = { label: string };

export type ChatMessageData = {
  id: number;
  role: "user" | "assistant";
  text: string;
  sources?: ChatSource[];
  limitations?: string[];
};

export function ChatMessage({ message }: { message: ChatMessageData }) {
  const isUser = message.role === "user";
  return (
    <article
      className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm leading-6 ${
        isUser
          ? "ml-auto bg-blue-600 text-white"
          : "border border-zinc-200 bg-white text-zinc-700"
      }`}
    >
      <p className="whitespace-pre-line">{message.text}</p>
      {message.sources?.length ? (
        <div className="mt-3 border-t border-zinc-100 pt-3">
          <p className="text-[11px] font-semibold text-zinc-500">확인한 근거</p>
          <ul className="mt-1 space-y-1 text-xs text-zinc-500">
            {message.sources.map((source, index) => (
              <li key={`${source.label}-${index}`}>{source.label}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {message.limitations?.length ? (
        <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
          {message.limitations.map((item, index) => (
            <p key={`${item}-${index}`}>{item}</p>
          ))}
        </div>
      ) : null}
    </article>
  );
}
