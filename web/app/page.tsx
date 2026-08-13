"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { search, exampleChips } from "@/lib/searchClient";
import type { SearchMode, SearchResponse } from "@/lib/types";

interface Msg {
  role: "user" | "bot";
  text?: string;
  data?: SearchResponse;
}

const MODES: { id: SearchMode; label: string; hint: string }[] = [
  { id: "fast", label: "⚡ 빠른 검색", hint: "OpenSearch · 핫" },
  { id: "comprehensive", label: "🗄️ 전체 검색", hint: "S3 Vectors · 전체" },
  { id: "hybrid", label: "🔀 하이브리드", hint: "둘 다 · 융합" },
];

export default function Page() {
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      role: "bot",
      text:
        "찾고 싶은 이미지를 문장으로 설명해 주세요. 입력 문장은 Cohere Embed v4로 임베딩되어 검색됩니다. 아래에서 검색 방식을 고를 수 있어요 — 빠른 검색(OpenSearch 핫 티어), 전체 검색(S3 Vectors 전체 카탈로그), 하이브리드(둘을 병행해 융합). 한글·영어 모두 가능합니다.",
    },
  ]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [loading, setLoading] = useState(false);
  const [showArch, setShowArch] = useState(false);
  const chips = exampleChips();
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, loading]);

  async function run(q: string) {
    const query = q.trim();
    if (!query || loading) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: query }]);
    setLoading(true);
    try {
      const data = await search(query, mode);
      setMsgs((m) => [...m, { role: "bot", data }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "bot", text: `⚠️ ${e?.message || "검색 실패"}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="top">
        <div className="logo">S3</div>
        <div>
          <h1>S3 Vectors × OpenSearch — 하이브리드 이미지 검색</h1>
          <div className="sub">
            Cohere Embed v4 (Amazon Bedrock) + S3 Vectors ·{" "}
            <a className="deck" href="../deck/index.html">
              First Call Deck →
            </a>{" "}
            ·{" "}
            <a className="deck" href="../presentation/index.html">
              상세 덱 →
            </a>
          </div>
        </div>
        <div className="badges">
          <button className="archbtn" onClick={() => setShowArch(true)}>
            🏗 아키텍처
          </button>
          <span className="pill live">LIVE · 하이브리드</span>
        </div>
      </header>

      {showArch && <ArchModal onClose={() => setShowArch(false)} />}

      <div className="chat" ref={chatRef}>
        {msgs.map((m, i) => (
          <Message key={i} msg={m} />
        ))}
        {msgs.length <= 1 && (
          <div className="chips">
            {chips.map((c) => (
              <button key={c.label} className="chip" onClick={() => run(c.text)}>
                {c.label}
              </button>
            ))}
          </div>
        )}
        {loading && (
          <div className="msg bot">
            <div className="avatar">🔎</div>
            <div className="bubble">
              <span className="spinner" /> {MODES.find((x) => x.id === mode)?.label} 검색 중…
            </div>
          </div>
        )}
      </div>

      <div className="composer">
        <div className="modes">
          {MODES.map((mm) => (
            <button
              key={mm.id}
              className={`mode-btn ${mode === mm.id ? "active" : ""}`}
              onClick={() => setMode(mm.id)}
            >
              {mm.label}
              <small>{mm.hint}</small>
            </button>
          ))}
        </div>
        <div className="inputrow">
          <input
            value={input}
            placeholder='예: "물 마시는 사람" · "녹색 재활용 심볼" · "음악 듣는 사람"'
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // 한글 IME 조합 중 Enter는 무시 (조합 중 제출 시 마지막 글자가 검색창에 남는 문제 방지)
              if (e.key !== "Enter") return;
              if (e.nativeEvent.isComposing || (e as any).keyCode === 229) return;
              run(input);
            }}
          />
          <button onClick={() => run(input)} disabled={loading || !input.trim()}>
            검색
          </button>
        </div>
      </div>
    </div>
  );
}

function Message({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="msg user">
        <div className="avatar">🧑</div>
        <div className="bubble">{msg.text}</div>
      </div>
    );
  }
  return (
    <div className="msg bot">
      <div className="avatar">🔎</div>
      <div className="bubble">
        {msg.text && <div>{msg.text}</div>}
        {msg.data && <Results data={msg.data} />}
      </div>
    </div>
  );
}

function Results({ data }: { data: SearchResponse }) {
  const t = data.timings;
  return (
    <>
      <div className="meta">
        {data.tiersQueried.map((tier) => (
          <span key={tier} className={`tier ${tier}`}>
            {tier === "opensearch" ? "OpenSearch (핫)" : "S3 Vectors (전체)"}
          </span>
        ))}
        <span className="timing">
          임베딩 {t.embed_ms}ms
          {t.opensearch_ms != null && ` · OS ${t.opensearch_ms}ms`}
          {t.s3vectors_ms != null && ` · S3V ${t.s3vectors_ms}ms`}
          {" · 총 "}
          {t.total_ms}ms
        </span>
        <span>· 결과 {data.results.length}개</span>
      </div>
      {data.results.length === 0 ? (
        <div style={{ color: "var(--muted)" }}>일치하는 결과가 없습니다. 다른 설명으로 검색해 보세요.</div>
      ) : (
        <div className="grid">
          {data.results.map((r) => (
            <a
              key={r.image_id}
              className="card"
              href={r.preview_url}
              target="_blank"
              rel="noreferrer"
              title={`${r.title}\n${r.keywords.split(",").slice(0, 8).join(", ")}`}
            >
              <span className={`tdot ${r.tier}`} title={r.tier === "opensearch" ? "OpenSearch" : "S3 Vectors"} />
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={r.thumb_url} alt={r.title} loading="lazy" />
              <div className="cap">
                <span>{r.title || r.image_id}</span>
                <span className="score">{(r.score * 100).toFixed(0)}%</span>
              </div>
            </a>
          ))}
        </div>
      )}
    </>
  );
}

// ── 아키텍처 모달 (S3 Vectors only · Mermaid) ─────────────────────────────
const ARCH_DIAGRAM = `flowchart TB
  U["👤 사용자 · 채팅 UI"] --> E["Cohere Embed v4 (Bedrock)"]
  E --> API["CloudFront /api/* → API GW → Lambda<br/>(비공개 · 시크릿 헤더)"]
  API --> RT{"모드<br/>fast · full · hybrid"}
  RT -->|"빠른"| OS[("OpenSearch<br/>핫 티어 · k-NN")]
  RT -->|"전체"| SV[("S3 Vectors<br/>전체 카탈로그")]
  RT -->|"하이브리드 (병행)"| BOTH([" "])
  BOTH --> OS
  BOTH --> SV
  OS --> F["융합 · 재랭킹<br/>(image_id 중복 제거)"]
  SV --> F
  F --> R["🖼️ 결과 그리드 · 유사도순"]`;

const ARCH_ITEMS: { title: string; body: ReactNode }[] = [
  {
    title: "① 채팅 UI (Next.js + TypeScript)",
    body: (
      <>
        사용자가 자연어로 이미지를 설명합니다(한글/영어). 정적 사이트로 CloudFront에서 서빙되며, 검색 요청만
        <code> /api/search</code>로 보냅니다.
      </>
    ),
  },
  {
    title: "② 쿼리 임베딩 · Cohere Embed v4 (Bedrock)",
    body: (
      <>
        쿼리를 <code>input_type: "search_query"</code>로 호출해 1024차원 벡터로 변환합니다. 저장된 이미지도 같은
        모델(<code>input_type: "image"</code>)로 임베딩되어 동일 공간에 있으므로 텍스트→이미지 검색이 됩니다.
      </>
    ),
  },
  {
    title: "③ CloudFront → 비공개 Lambda (보안)",
    body: (
      <>
        <code>/api/*</code> 경로는 CloudFront가 <b>OAC(SigV4)</b>로 서명해 Lambda Function URL을 호출합니다.
        Function URL은 <b>AuthType=AWS_IAM(비공개)</b>이라 퍼블릭 인터넷에서 직접 호출할 수 없고, 오직 이
        배포판만 호출할 수 있습니다. 브라우저에는 자격 증명이 노출되지 않습니다.
      </>
    ),
  },
  {
    title: "④ 라우터 · 3가지 검색 모드",
    body: (
      <>
        <b>빠른 검색</b>은 OpenSearch 핫 티어만, <b>전체 검색</b>은 S3 Vectors 전체 카탈로그만 조회합니다.
        <b>하이브리드</b>는 두 티어를 <b>병행(parallel)</b>으로 조회한 뒤 <code>image_id</code>로 중복을
        제거하고 최고 점수 기준으로 재랭킹합니다.
      </>
    ),
  },
  {
    title: "⑤ OpenSearch (핫 티어) — 관리형 도메인",
    body: (
      <>
        관리형 Amazon OpenSearch Service 도메인(t3.small.search)에 인기 이미지의 소수 부분집합을 k-NN(cosine,
        lucene)으로 색인합니다. Lambda가 SigV4(<code>es</code>)로 서명해 <code>_search</code>를 호출합니다.
        낮은 지연의 인터랙티브 검색을 담당합니다.
      </>
    ),
  },
  {
    title: "⑥ Amazon S3 Vectors (전체 카탈로그)",
    body: (
      <>
        <code>query_vectors</code>로 전체 카탈로그를 코사인 유사도 검색합니다(top-K). 서버리스, 11-9 내구성,
        대규모에서 상시 가동형 벡터 DB 대비 약 90% 저렴. 현재 약 500장이 색인되어 있고, 그중 일부가 핫 티어로
        승격되어 OpenSearch에도 존재합니다.
      </>
    ),
  },
  {
    title: "⑦ 비필터 메타데이터 · 데이터 적재",
    body: (
      <>
        URL·키워드·제목처럼 큰 필드는 <b>비필터(non-filterable)</b> 메타데이터로 저장해 필터 가능 한도를 지키고
        쿼리 데이터 처리 비용을 낮췄습니다.
      </>
    ),
  },
];

function ArchModal({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState<number | null>(2);
  const diagramRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
    const renderDiagram = async () => {
      const m = (window as any).mermaid;
      if (!m || !diagramRef.current) return;
      try {
        m.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "loose",
          fontFamily: "Malgun Gothic, Apple SD Gothic Neo, Segoe UI, sans-serif",
          themeVariables: {
            primaryColor: "#17223b",
            primaryTextColor: "#eaf1ff",
            primaryBorderColor: "#3a4a6b",
            lineColor: "#ff9900",
            clusterBkg: "#0f1830",
            fontSize: "17px",
          },
          flowchart: { htmlLabels: true, curve: "basis", nodeSpacing: 55, rankSpacing: 60, padding: 12 },
        });
        const { svg } = await m.render("demo_arch", ARCH_DIAGRAM);
        if (diagramRef.current) diagramRef.current.innerHTML = svg;
      } catch (e) {
        console.error(e);
      }
    };
    if ((window as any).mermaid) {
      renderDiagram();
    } else {
      const s = document.createElement("script");
      s.src = `${base}/vendor/mermaid.min.js`;
      s.onload = renderDiagram;
      document.body.appendChild(s);
    }
  }, []);

  return (
    <div className="modal-back" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="mhead">
          <h2>🏗 데모 아키텍처 (하이브리드)</h2>
          <button className="mclose" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>
        <div className="msub">
          입력 문장을 실시간 임베딩해 OpenSearch(핫 티어)와 S3 Vectors(전체)를 병행 검색하고 융합합니다.
          아래 항목을 클릭하면 상세 설명이 열립니다.
        </div>

        <div className="diagram-card">
          <div className="mermaid" ref={diagramRef} />
        </div>

        <div className="acc">
          {ARCH_ITEMS.map((it, i) => (
            <div key={i} className={`acc-item ${open === i ? "open" : ""}`}>
              <button className="acc-head" onClick={() => setOpen(open === i ? null : i)}>
                {it.title}
                <span className="chev">›</span>
              </button>
              <div className="acc-body">{it.body}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
