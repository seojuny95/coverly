import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { BrandNavigation } from "./brand-navigation";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Coverly AI — 보험은 흩어져 있어도, 이해는 한 번에",
  description:
    "여러 보험사에 나뉜 가입 내역을 AI가 찾아 연결하고, 보장 범위와 중복을 근거와 함께 분석해요.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>
          <BrandNavigation />
          {children}
        </Providers>
      </body>
    </html>
  );
}
