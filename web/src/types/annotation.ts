export type SectionLabel = 'intro' | 'main' | 'build' | 'breakdown' | 'outro' | 'unknown'
export type ElementName = 'drums' | 'vocal' | 'bass' | 'melody'
export type ElementState = 'absent' | 'background' | 'foreground' | 'entering' | 'ending' | 'unknown'
export type AnnotationTaskId = 'structure.section_label' | `elements.${ElementName}.state`
export type AnnotationValue = SectionLabel | ElementState
export type AnnotationStatus = 'candidate' | 'annotated' | 'reviewed' | 'adjudicated' | 'rejected'

export interface AnnotationRecord {
  schema_name: 'harbeat.annotation_record'
  schema_version: '1.0.0'
  annotation_id: string
  dataset_version: string
  track_id: string
  task_id: AnnotationTaskId
  granularity: 'section' | 'bar'
  start_sec: number
  end_sec: number
  start_bar_index: number
  end_bar_index: number
  value: AnnotationValue
  annotator_id: string
  annotation_status: AnnotationStatus
  annotator_confidence: number | null
  candidate_source: string | null
  created_at: string
}

export interface SectionCandidate {
  value: SectionLabel
  confidence: number | null
  source: string | null
  source_label: string | null
}

export interface ElementCandidate {
  value: ElementState
  activity: number | null
  confidence: number | null
  source: string | null
}

export interface CandidateBar {
  bar_index: number
  start_sec: number
  end_sec: number
  beat_times_sec: number[]
  is_partial: boolean
  section: SectionCandidate
  elements: Record<ElementName, ElementCandidate>
}

export interface SectionAnnotationBlock {
  block_id: string
  start_bar_index: number
  end_bar_index: number
  start_time: number
  end_time: number
  raw_start_time: number
  raw_end_time: number
  start_snap_error_sec: number
  end_snap_error_sec: number
  source: 'songformer_bar_snap_v1'
  source_segment_indexes: number[]
  needs_review: boolean
  suppressed_boundary_count: number
  model_runtime_fingerprint: string
}

export interface SectionModelState {
  model: 'ASLP-lab/SongFormer'
  status: 'ready' | 'failed'
  cache_namespace: string | null
  runtime_fingerprint: Record<string, unknown>
  error: string | null
}

export interface SectionRelabelerState {
  enabled: false
  mode: 'disabled'
  model_status: 'not_installed'
  model_version: null
  input_contract_version: 'songformer_section_relabeler_input_v1'
  output_contract_version: 'songformer_section_relabeler_output_v1'
}

export interface AnnotationWorkspace {
  schema_name: 'harbeat.annotation_workspace'
  schema_version: '1.0.0'
  dataset_version: string
  track_id: string
  title: string
  artist: string
  duration_sec: number
  timeline_fingerprint: string
  timeline_warnings: string[]
  revision: number
  annotations: AnnotationRecord[]
  bars: CandidateBar[]
  section_block_status: 'ready' | 'needs_review' | 'failed' | 'not_analyzed'
  section_blocks: SectionAnnotationBlock[]
  section_model: SectionModelState | null
  section_relabeler: SectionRelabelerState
  updated_at: string | null
}

export interface SaveAnnotationWorkspaceRequest {
  dataset_version: string
  revision: number
  annotations: AnnotationRecord[]
}

export interface AnnotationDraft {
  datasetVersion: string
  trackId: string
  annotatorId: string
  bars: CandidateBar[]
  annotations: AnnotationRecord[]
}

export interface BarRange {
  start: number
  end: number
}

export interface PilotTrackSummary {
  id: string
  title: string
  artist: string
  duration_sec: number
  stems_available: Array<'vocals' | 'drums' | 'bass' | 'other'>
}
