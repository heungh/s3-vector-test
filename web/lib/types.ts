export type SearchMode = "fast" | "comprehensive" | "hybrid";
export type SourceTier = "opensearch" | "s3vectors";

export interface ImageResult {
  image_id: string;
  title: string;
  keywords: string;
  thumb_url: string;
  preview_url: string;
  score: number; // similarity [0,1]
  tier: SourceTier;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  results: ImageResult[];
  timings: { embed_ms: number; opensearch_ms?: number; s3vectors_ms?: number; total_ms: number };
  tiersQueried: SourceTier[];
}
