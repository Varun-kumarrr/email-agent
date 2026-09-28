// TypeScript mirrors of the FastAPI response/request schemas.

export type SecurityType = "NONE" | "STARTTLS" | "SSL_TLS";
export type EmailFormat = "HTML" | "PLAIN_TEXT";
export type EmailStatus = "SENT" | "FAILED";
export type Tone = "professional" | "friendly" | "formal" | "persuasive" | "concise";

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
}

export interface SendEmailInput {
  recipient: string;
  subject: string;
  body: string;
  format: EmailFormat;
  cc: string[];
  bcc: string[];
  append_signature: boolean | null;
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
}

export interface EmailHistoryItem {
  id: string;
  sender_email: string;
  sender_name: string | null;
  recipient: string;
  cc: string[];
  bcc: string[];
  subject: string;
  body: string;
  email_format: EmailFormat;
  status: EmailStatus;
  error_message: string | null;
  attempts: number;
  created_at: string;
  sent_at: string | null;
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
