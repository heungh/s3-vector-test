import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amazon S3 Vectors — 시맨틱 이미지 검색",
  description:
    "Amazon Bedrock의 Cohere Embed v4로 임베딩하고 Amazon S3 Vectors에서 의미 기반으로 검색하는 이미지 검색 데모.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
