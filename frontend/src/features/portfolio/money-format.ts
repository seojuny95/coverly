export function formatKoreanWon(amount: number) {
  if (!Number.isFinite(amount)) return "금액 확인 필요";
  if (amount === 0) return "0원";

  const sign = amount < 0 ? "-" : "";
  let remaining = Math.round(Math.abs(amount));
  const parts: string[] = [];

  const eok = Math.floor(remaining / 100_000_000);
  if (eok > 0) {
    parts.push(`${eok.toLocaleString("ko-KR")}억`);
    remaining %= 100_000_000;
  }

  const man = Math.floor(remaining / 10_000);
  if (man > 0) {
    parts.push(`${man.toLocaleString("ko-KR")}만원`);
    remaining %= 10_000;
  }

  const cheon = Math.floor(remaining / 1_000);
  if (cheon > 0) {
    parts.push(`${cheon.toLocaleString("ko-KR")}천원`);
    remaining %= 1_000;
  }

  if (remaining > 0) {
    parts.push(`${remaining.toLocaleString("ko-KR")}원`);
  }

  return `${sign}${parts.join(" ")}`;
}
