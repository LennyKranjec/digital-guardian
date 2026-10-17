/** Minimale Antwortformen (nur die Felder, die der Kernpfad prüft). */

export interface Row {
  patient_id: string;
  pseudonym: string;
  traffic_light: string;
  open_alerts: number;
}

export interface AlertDto {
  alert_id: string;
  rule_id: string;
  level: string;
  status: string;
  symptom_key: string | null;
  notified: boolean;
  acknowledgement: { by: string; decision: string; note: string | null } | null;
}

export interface NotificationDto {
  patient_id: string;
  level: string;
  text: string;
}

export interface QuestionnaireDto {
  items: {
    symptom_key: string;
    questions: {
      attribute: string;
      text: string;
      options: { value: number; label: string }[];
    }[];
  }[];
}

export interface TemplateTerm {
  ctcae_term_id: string;
  grades: Record<string, string>;
}

export interface TemplateDto {
  terms: TemplateTerm[];
}

export interface AssessmentDto {
  assessment_id: string;
  fact_id: string;
  items: { ctcae_term_id: string; grade: number }[];
}

export interface OverviewDto {
  persisting: boolean;
  traffic_light: string;
}

export interface BundleEntry {
  resource: { resourceType: string };
}

export interface BundleDto {
  resourceType: string;
  type: string;
  entry: BundleEntry[];
}
