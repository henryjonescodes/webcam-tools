export interface CamEvent {
  id: string;
  type: string;
  timestamp: number;
  meta: Record<string, unknown>;
  video: string | null;
  flagged: boolean;
}

export interface DetectorStatus {
  name: string;
  enabled: boolean;
  heavy: boolean;
  links: Record<string, boolean>;
}

export interface ActionStatus {
  name: string;
  enabled: boolean;
}

export interface Status {
  connected: boolean;
  paused: boolean;
  recording: boolean;
  shutting_down: boolean;
  camera_index: number;
  camera_name: string | null;
  fps: number;
  detectors: DetectorStatus[];
  actions: ActionStatus[];
}

export async function getStatus(): Promise<Status> {
  const res = await fetch("/api/status");
  return res.json();
}

export async function getEvents(limit = 50): Promise<CamEvent[]> {
  const res = await fetch(`/api/events?limit=${limit}`);
  return res.json();
}

export async function toggleDetector(name: string, enabled: boolean): Promise<DetectorStatus> {
  const res = await fetch(`/api/detectors/${name}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export async function toggleAction(name: string, enabled: boolean): Promise<ActionStatus> {
  const res = await fetch(`/api/actions/${name}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export async function togglePipelineLink(
  detectorName: string,
  actionName: string,
  enabled: boolean
): Promise<{ detector: string; action: string; enabled: boolean }> {
  const res = await fetch(`/api/pipeline/${detectorName}/${actionName}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export async function getWebhookUrl(): Promise<{ url: string | null }> {
  const res = await fetch("/api/webhook");
  return res.json();
}

export async function setWebhookUrl(url: string): Promise<{ url: string | null }> {
  const res = await fetch("/api/webhook", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url || null }),
  });
  return res.json();
}

export async function openRecordingsFolder(): Promise<{ opened: string }> {
  const res = await fetch("/api/system/open-recordings-folder", { method: "POST" });
  if (!res.ok) throw new Error(`open-recordings-folder -> ${res.status}`);
  return res.json();
}

export interface ToggleEntry {
  name: string;
  enabled: boolean;
}

export interface Toggles {
  detectors: ToggleEntry[];
  actions: ToggleEntry[];
  image: ToggleEntry[];
  classes: ToggleEntry[];
}

export async function getToggles(): Promise<Toggles> {
  const res = await fetch("/api/toggles");
  return res.json();
}

export async function toggleGeneric(
  category: "detectors" | "actions" | "image" | "classes",
  name: string,
  enabled: boolean
): Promise<ToggleEntry> {
  const res = await fetch(`/api/toggles/${category}/${name}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return res.json();
}

export interface CameraDevice {
  index: number;
  name: string;
}

export async function getCameras(): Promise<{ devices: CameraDevice[]; current: number }> {
  const res = await fetch("/api/cameras");
  return res.json();
}

export async function selectCamera(index: number): Promise<{ index: number }> {
  const res = await fetch("/api/camera/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  return res.json();
}

export async function pauseCamera(paused: boolean): Promise<{ paused: boolean }> {
  const res = await fetch("/api/camera/pause", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused }),
  });
  return res.json();
}

export async function setEventFlag(id: string, flagged: boolean): Promise<{ id: string; flagged: boolean }> {
  const res = await fetch(`/api/events/${id}/flag`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flagged }),
  });
  return res.json();
}

export async function deleteEvent(id: string): Promise<{ id: string; deleted: boolean }> {
  const res = await fetch(`/api/events/${id}`, { method: "DELETE" });
  return res.json();
}

export async function clearUnflaggedEvents(): Promise<{ deleted: number }> {
  const res = await fetch("/api/events/clear-unflagged", { method: "POST" });
  return res.json();
}

export interface Adjustments {
  brightness: number;
  contrast: number;
  saturation: number;
}

export async function getAdjustments(): Promise<Adjustments> {
  const res = await fetch("/api/camera/adjustments");
  return res.json();
}

export async function setAdjustments(partial: Partial<Adjustments>): Promise<Adjustments> {
  const res = await fetch("/api/camera/adjustments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(partial),
  });
  return res.json();
}

export interface HardwareSettings {
  auto_exposure: boolean;
  exposure: number;
  brightness: number;
  camera_name: string | null;
}

export async function getHardware(): Promise<HardwareSettings> {
  const res = await fetch("/api/camera/hardware");
  return res.json();
}

export async function setHardware(
  partial: Partial<Omit<HardwareSettings, "camera_name">>
): Promise<HardwareSettings> {
  const res = await fetch("/api/camera/hardware", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(partial),
  });
  return res.json();
}

export type Rotation = 0 | 90 | 180 | 270;

export async function getRotation(): Promise<{ rotation: Rotation }> {
  const res = await fetch("/api/camera/rotation");
  return res.json();
}

export async function setRotation(rotation: Rotation): Promise<{ rotation: Rotation }> {
  const res = await fetch("/api/camera/rotation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rotation }),
  });
  return res.json();
}
