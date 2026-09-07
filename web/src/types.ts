export type Status = "idle" | "running" | "at_risk" | "wrapped" | "error";

export type EventType =
  | "connected"
  | "day_start"
  | "setup_wrapped"
  | "scene_wrapped"
  | "meal_break"
  | "recovery"
  | "wrapped"
  | "error";

export interface ProvisioningInfo {
  dashboard_uid: string;
  dashboard_url: string;
  alert_rule_uid: string;
  alert_rule_url: string;
  burn_rate_threshold: number;
  evaluation_window_minutes: number;
  annotation: string;
  provisioned_at: string;
}

export interface ProvisioningSnapshot {
  info: ProvisioningInfo;
  live: boolean;
}

export interface Violation {
  rule: "turnaround" | "meal" | "minors" | "crew_rest";
  performer_id: string | null;
  reason: string;
}

export interface GateVerdict {
  option_id: string;
  approved: boolean;
  violations: Violation[];
}

export interface RecoveryOption {
  id: string;
  kind: "reorder" | "drop_coverage" | "move_to_pickups" | "flip_to_cover_set";
  description: string;
  affected_scenes: string[];
  minutes_recovered: number;
}

export interface RecoveryCycleResult {
  options: RecoveryOption[];
  verdicts: GateVerdict[];
  incident_id: string | null;
  live: boolean;
}

export interface RecoverySnapshot {
  result: RecoveryCycleResult;
  incident_url: string | null;
}

export type StripColor = "day-int" | "day-ext" | "night-int" | "night-ext";

export interface SceneSnapshot {
  number: string;
  synopsis: string;
  page_eighths_display: string;
  strip_color: StripColor;
  cast_names: string[];
}

export interface TimelineSnapshot {
  call_label: string;
  overtime_label: string;
  elapsed_fraction: number;
  meal_fraction: number;
  golden_hour_fraction: number;
  projected_wrap_fraction: number;
  projected_wrap_label: string;
}

export interface PaceSnapshot {
  actual_points: [number, number][];
  behind_label: string | null;
}

export interface CastClockSnapshot {
  character_name: string;
  hours_worked: number;
  turnaround_fraction: number;
  is_tight: boolean;
}

export interface DaySnapshot {
  run_id: number;
  event_type: EventType;
  status: Status;
  error_message: string | null;
  day_number: number;
  total_days: number;
  production_title: string;
  provisioning: ProvisioningSnapshot | null;
  scenes: SceneSnapshot[];
  current_scene: string | null;
  shot_scene_numbers: string[];
  clock: string | null;
  pages_completed_eighths: number;
  pages_remaining_eighths: number;
  total_page_eighths: number;
  setups_completed: number;
  setups_total: number;
  error_budget_consumed: number;
  burn_rate: number;
  projected_wrap: string | null;
  recovery: RecoverySnapshot | null;
  timeline: TimelineSnapshot;
  pace: PaceSnapshot;
  cast_clocks: CastClockSnapshot[];
  verdict_headline: string;
  verdict_subline: string;
  budget_sentence: string;
  burn_sentence: string;
  pages_sentence: string;
  cost_of_delay_sentence: string;
}
