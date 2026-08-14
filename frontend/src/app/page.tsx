import { HomeHero } from "./_components/home-hero";
import { TrustPrinciples } from "./_components/trust-principles";
import { BrandLink } from "@/shared/components/brand";

export default function HomePage() {
  return (
    <>
      <BrandLink className="absolute top-6 left-6 z-40 lg:left-8" />
      <main className="overflow-hidden bg-white text-zinc-950">
        <HomeHero />
        <TrustPrinciples />
      </main>
    </>
  );
}
