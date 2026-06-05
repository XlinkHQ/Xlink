import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "XLink Console",
  description: "XLink provider-aware node and subscription management console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
