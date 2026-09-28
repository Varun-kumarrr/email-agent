import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Email Agent",
  description: "Company profile, SMTP configuration and AI-assisted email sending",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
