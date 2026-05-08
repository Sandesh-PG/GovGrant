export type User = {
  id: string;
  email: string;
  name: string;
};

export type ChatSession = {
  session_id: string;
  status: 'intake' | 'researching' | 'validating' | 'done';
  created_at: string;
};

export type UserProfile = {
  name: string;
  type: string;
  sector: string;
  state: string;
  city: string;
  team_size: number;
  revenue_inr: number;
  funding_purpose: string;
  session_id?: string;
};

export type Scheme = {
  scheme_name: string;
  source_url: string;
  source_type: string;
  criteria_text: string;
  deadline?: string;
  max_revenue_inr?: number;
  eligible_types: string;
};

export type RankedScheme = {
  scheme_name: string;
  match_score: number;
  rank: number;
  reason: string;
  urgency_score: number;
  composite_rank: number;
  portal_url?: string;
  deadline?: string;
  grant_amount?: string;
};

export type DocumentItem = {
  name: string;
  description: string;
  mandatory: boolean;
};

export type ActionCard = {
  scheme_name: string;
  portal_url: string;
  deadline?: string;
  steps: string[];
  estimated_days: number;
  tips: string[];
};

export type GrantReport = {
  session_id: string;
  schemes: RankedScheme[];
  documents: DocumentItem[];
  action_cards: ActionCard[];
  cover_summary: string;
  created_at: string;
};

export type SSEEvent = {
  type: 'intake_done' | 'research_done' | 'validation_done' | 'report_ready' | 'chat' | 'error';
  data: any;
};
