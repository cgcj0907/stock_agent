export interface CustomWorkflowStep {
  id: string;
  agent: string;
  deps: string[];
}

export interface CustomWorkflow {
  id: string;
  user_id: string;
  name: string;
  description: string;
  steps: CustomWorkflowStep[];
  created_at: string;
  updated_at: string;
}

export interface CustomWorkflowInput {
  name: string;
  description: string;
  steps: CustomWorkflowStep[];
}
