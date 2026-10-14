// Mirrors the FastAPI v1 contracts. Regenerate full types with `npm run gen:types`.
export type Me = {
  user_id: string; email: string; display_name: string | null; tenant_id: string; tenant_name: string;
  role: "owner" | "admin" | "member"; auth_mode: string; salesforce_mode: string; ai_provider: string;
};
export type SyncRun = {
  id: string; status: string; objects_seen: number; fields_seen: number; relationships_seen: number;
  error_count: number; started_at: string | null; completed_at: string | null; error_detail?: string | null;
};
export type Connection = {
  id: string; org_id: string; org_name: string | null; instance_url: string; sf_username: string | null;
  mode: string; status: string; scopes: string[]; api_version: string; last_sync_at: string | null;
  catalog_version: string | null; latest_sync: SyncRun | null;
};
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type CatalogObject = {
  api_name: string; label: string; label_plural: string | null; is_custom: boolean; is_queryable: boolean;
  is_active: boolean; field_count: number; metadata_version: string | null;
};
export type Field = {
  api_name: string; label: string; data_type: string; reference_to: string[]; relationship_name: string | null;
  is_custom: boolean; is_filterable: boolean; is_groupable: boolean; is_sortable: boolean; is_aggregatable: boolean;
  is_active: boolean; picklist_values: string[];
};
export type Relationship = {
  relationship_name: string; direction: "parent" | "child"; related_object: string; relationship_type: string;
  field: string | null; in_catalog: boolean; soql_hint: string;
};
export type ObjectDetail = CatalogObject & { key_prefix: string | null; fields: Field[]; relationships: Relationship[] };
export type Issue = { code: string; message: string; severity: "error" | "warning"; path: string | null };
export type Validation = {
  valid: boolean; issues: Issue[]; normalized_soql: string | null; root_object: string | null;
  referenced_objects: string[]; referenced_fields: string[]; is_aggregate: boolean; checks: string[];
};
export type PlanResponse = {
  execution_id: string; status: "validated" | "rejected"; source: "ai" | "template"; question: string;
  plan: Record<string, unknown> | null; soql: string | null; explanation: string | null; validation: Validation;
  context_objects: string[]; template: { id: string; name: string; score: number; parameters: Record<string, unknown> } | null;
  model: string | null; token_usage: { input_tokens: number; output_tokens: number } | null; correlation_id: string;
};
export type ExecuteResponse = {
  execution_id: string; status: string; soql: string; columns: string[]; rows: Record<string, unknown>[];
  row_count: number; total_size: number; duration_ms: number; cached: boolean; explanation: string | null;
  source: string; warnings: Issue[]; correlation_id: string;
};
export type SavedQuery = {
  id: string; name: string; description: string | null; template: string;
  parameters_schema: Record<string, { type: string; default?: unknown; enum?: string[]; minimum?: number; maximum?: number }>;
  question_examples: string[]; version: number; visibility: "private" | "tenant"; owner_id: string; use_count: number;
  created_at: string; updated_at: string;
};
export type HistoryItem = {
  id: string; question: string | null; soql: string | null; status: string; source: string; interface: string;
  row_count: number | null; duration_ms: number | null; model: string | null;
  token_usage: { input_tokens?: number; output_tokens?: number } | null; created_at: string; correlation_id: string | null;
};
export type AuditItem = {
  id: string; action: string; result: string; resource_type: string | null; resource_id: string | null;
  user_id: string | null; correlation_id: string | null; created_at: string; metadata: Record<string, unknown>;
};
export type Metrics = {
  oauth: { success: number; failure: number };
  metadata_sync: { runs: number; avg_duration_s: number; errors: number };
  queries: { total: number; by_status: Record<string, number>; by_source: Record<string, number>;
             validation_rejection_rate: number; avg_execution_ms: number; p95_execution_ms: number };
  ai: { requests: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number; avg_latency_ms: number };
  saved_query_reuse_rate: number; mcp_tool_calls: Record<string, number>;
  salesforce_api_calls_today: Record<string, number>;
};
