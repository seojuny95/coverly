import { HomeHero } from "./_components/home-hero";
import { TrustPrinciples } from "./_components/trust-principles";

export default function HomePage() {
  return (
    <main className="overflow-hidden bg-white text-zinc-950">
      <HomeHero />
      <TrustPrinciples />
    </main>
  );
}
