import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "P6 Intelligence — Schedule comparison",
  description: "Compare Primavera P6 schedule updates and trace dependency changes with source-level evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
