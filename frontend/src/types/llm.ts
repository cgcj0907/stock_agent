export interface LlmSetting {
  id: string;
  provider: string;
  name: string;
  base_url: string;
  model: string;
  api_key_masked: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface LlmSettingInput {
  provider: string;
  name: string;
  base_url: string;
  model: string;
  api_key: string;
  is_default: boolean;
}
