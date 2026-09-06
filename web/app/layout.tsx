import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "P6 Intelligence — Schedule comparison",
  description: "Trace activity, relationship, and downstream milestone changes with source evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
