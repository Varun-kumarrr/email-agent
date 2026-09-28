// TypeScript mirrors of the FastAPI response/request schemas.

export type SecurityType = "NONE" | "STARTTLS" | "SSL_TLS";
export type EmailFormat = "HTML" | "PLAIN_TEXT";
export type EmailStatus = "QUEUED" | "SENDING" | "RETRYING" | "SENT" | "FAILED";
export const FINAL_STATUSES: EmailStatus[] = ["SENT", "FAILED"];
export type Tone = "professional" | "friendly" | "formal" | "persuasive" | "concise";
export type EmailProviderName = "GMAIL" | "OUTLOOK" | "GENERIC";
export type AccountType = "SMTP" | "OAUTH";

export interface User {
  id: string;
  email: string;
  name: string;
  has_company: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface ServiceItem {
  name: string;
  description?: string | null;
}
export interface TargetCustomerItem {
  segment: string;
  description?: string | null;
}
export interface ValuePropositionItem {
  statement: string;
}
export interface SocialLinkItem {
  platform: string;
  url: string;
}

export interface CompanyInput {
  name: string;
  description: string;
  website: string | null;
  industry: string | null;
  location: string | null;
  contact_person: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  address: string | null;
  services: ServiceItem[];
  target_customers: TargetCustomerItem[];
  value_propositions: ValuePropositionItem[];
  social_links: SocialLinkItem[];
}

export interface Company extends CompanyInput {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface EmailConfigInput {
  email: string;
  smtp_host: string;
  smtp_port: number;
  username: string;
  password?: string | null; // write-only
  security_type: SecurityType;
  sender_name: string;
  reply_to: string | null;
}

export interface EmailConfig {
  email: string;
  smtp_host: string;
  smtp_port: number;
  username: string;
  security_type: SecurityType;
  sender_name: string;
  reply_to: string | null;
  password_configured: boolean; // the password itself is never returned
  last_tested_at: string | null;
  last_test_success: boolean | null;
  updated_at: string;
}

export interface SmtpTestResult {
  success: boolean;
  message: string;
  error_code: string | null;
  tested_at: string;
}

export interface EmailAccount {
  id: string;
  account_name: string;
  provider: EmailProviderName;
  account_type: AccountType;
  email_address: string;
  sender_name: string;
  reply_to: string | null;
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_username: string | null;
  security_type: SecurityType | null;
  password_configured: boolean; // passwords and OAuth tokens are never returned
  oauth_connected: boolean;
  oauth_token_expires_at: string | null;
  is_active: boolean;
  is_default: boolean;
  last_tested_at: string | null;
  last_test_success: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface EmailAccountCreate {
  account_name: string;
  provider: EmailProviderName;
  email_address: string;
  sender_name: string;
  reply_to: string | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
  password: string; // write-only
  security_type?: SecurityType | null;
  is_active?: boolean;
  is_default?: boolean;
}

export type EmailAccountUpdate = Partial<Omit<EmailAccountCreate, "provider" | "is_default">>;

export interface EmailTemplate {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  subject_template: string;
  body_template: string;
  content_type: EmailFormat;
  variables: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateInput {
  name: string;
  description: string | null;
  category: string | null;
  subject_template: string;
  body_template: string;
  content_type: EmailFormat;
  is_active: boolean;
}

export interface TemplatePreview {
  subject: string;
  body: string;
  content_type: EmailFormat;
  variables_used: Record<string, string>;
  missing_variables: string[];
}

export interface SignatureInput {
  signature_text: string;
  enabled: boolean;
  append_automatically: boolean;
}

export interface Signature extends SignatureInput {
  updated_at: string;
}

export interface PreferencesInput {
  sender_name: string | null;
  reply_to: string | null;
  default_format: EmailFormat;
  daily_send_limit: number;
  max_recipients_per_email: number;
  max_send_retries: number;
  default_cc: string[];
  default_bcc: string[];
  extra_settings: Record<string, string | number | boolean | null>;
}

export interface Preferences extends PreferencesInput {
  effective_sender_name: string | null;
  effective_reply_to: string | null;
  signature: { configured: boolean; enabled: boolean; append_automatically: boolean };
  sent_today: number;
  remaining_today: number;
  updated_at: string | null;
}

export interface GenerateEmailInput {
  recipient_name: string;
  recipient_email: string;
  purpose: string;
  tone: Tone;
  additional_instructions: string | null;
  email_account_id?: string | null;
  template_id?: string | null;
  template_variables?: Record<string, string>;
}

export interface GeneratedEmail {
  subject: string;
  body: string;
  recipient_email: string;
  provider: string;
  fallback_used: boolean;
  warning: string | null;
  signature_policy: "appended_on_send" | "include_in_body" | "none";
  signature_preview: string | null;
  suggested_format: EmailFormat;
  suggested_cc: string[];
  suggested_bcc: string[];
  template_id: string | null;
  missing_template_variables: string[];
}

export interface SendEmailInput {
  recipient: string;
  subject: string;
  body: string;
  format: EmailFormat;
  cc: string[];
  bcc: string[];
  append_signature: boolean | null;
  email_account_id?: string | null;
}

export interface SendEmailResult {
  id: string;
  status: EmailStatus;
  message: string;
  sender_email: string;
  sender_name: string | null;
  recipient: string;
  cc: string[];
  bcc: string[];
  subject: string;
  format: EmailFormat;
  signature_appended: boolean;
  attempts: number;
  sent_at: string | null;
  task_id: string | null;
}

export interface EmailHistoryItem {
  id: string;
  email_account_id: string | null;
  sender_email: string;
  sender_name: string | null;
  reply_to: string | null;
  recipient: string;
  cc: string[];
  bcc: string[];
  subject: string;
  body: string;
  email_format: EmailFormat;
  status: EmailStatus;
  error_message: string | null;
  error_code: string | null;
  attempts: number;
  created_at: string;
  last_attempt_at: string | null;
  sent_at: string | null;
  is_test: boolean; // sent by an account's Test action
}

export interface EmailHistoryPage {
  items: EmailHistoryItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface FieldError {
  field: string;
  message: string;
}
