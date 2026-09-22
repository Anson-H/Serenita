

export type FavoriteSourceType = "message" | "report";

export type Favorite = {
  member_id: string | null;
  member_name: string | null;
  favorite_id: string;
  source_type: FavoriteSourceType;
  source_session_id?: string;
  source_id: string;
  title: string;
  content_summary: string;
  content_snapshot?: string;
  source_available?: boolean;
  tags: string[];
  created_at: string;
  updated_at?: string;
};
