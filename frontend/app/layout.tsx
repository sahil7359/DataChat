import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataChat",
  description: "Ask open data in plain English. Safe, grounded, verified SQL.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
