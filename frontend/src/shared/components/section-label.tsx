export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-2 font-mono text-[10px] font-medium tracking-[0.08em] text-zinc-500 sm:text-[11px]">
      <span className="size-1.5 bg-blue-600" aria-hidden="true" />
      {children}
    </p>
  );
}
