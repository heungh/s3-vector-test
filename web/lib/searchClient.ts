import type { SearchMode, SearchResponse } from "./types";

// Live search endpoint. Served same-origin via CloudFront (/api/*) which proxies to the
// private Lambda (via API Gateway + secret header). Override with NEXT_PUBLIC_SEARCH_ENDPOINT.
const ENDPOINT = process.env.NEXT_PUBLIC_SEARCH_ENDPOINT || "/api/search";

export async function search(query: string, mode: SearchMode = "hybrid"): Promise<SearchResponse> {
  const url = `${ENDPOINT}?q=${encodeURIComponent(query)}&mode=${mode}&topK=12`;
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) {
    let msg = `검색 실패 (${res.status})`;
    try {
      const j = await res.json();
      if (j?.error) msg = j.error;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// Example query chips (S3 Vectors semantic search; EN + KO both work via Cohere Embed v4).
export function exampleChips(): { label: string; text: string }[] {
  return [
    { label: "♻️ 재활용 심볼", text: "green recycling symbol" },
    { label: "💧 물 마시는 사람", text: "person drinking water" },
    { label: "📈 비즈니스 성장", text: "business growth arrow chart" },
    { label: "🤝 팀워크", text: "people teamwork hands together" },
    { label: "🎧 음악 듣기", text: "young woman listening to music" },
    { label: "🌳 자연 / 나무", text: "green tree nature forest" },
    { label: "🏃 달리기", text: "people running marathon" },
    { label: "환경보호 지구", text: "earth globe environment protection" },
  ];
}
