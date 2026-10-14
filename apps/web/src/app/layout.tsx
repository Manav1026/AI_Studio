import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Salesforce AI Workspace",
  description: "Governed natural-language access to Salesforce",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen text-sm">{children}</body>
    </html>
  );
}
