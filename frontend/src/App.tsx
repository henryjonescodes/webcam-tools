import { useEffect, useRef, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  Adjustments,
  CamEvent,
  CameraDevice,
  HardwareSettings,
  Rotation,
  Status,
  deleteEvent,
  getAdjustments,
  getCameras,
  getEvents,
  getHardware,
  getRotation,
  getStatus,
  getToggles,
  getWebhookUrl,
  openRecordingsFolder,
  pauseCamera,
  selectCamera,
  setAdjustments,
  setEventFlag,
  setHardware,
  setRotation,
  setWebhookUrl,
  toggleAction,
  toggleDetector,
  toggleGeneric,
  togglePipelineLink,
  ToggleEntry,
} from "./api";
import SliderRow from "./SliderRow";
import ToggleSwitch from "./ToggleSwitch";

function timeAgo(ts: number): string {
  const seconds = Math.floor(Date.now() / 1000 - ts);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

// clips still get their thumbnail extracted after ~10s of recording; treat
// anything newer as "not ready yet" instead of letting the <img> 404.
const THUMBNAIL_PENDING_SECONDS = 12;

const THUMBNAIL_FALLBACK =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="56" height="42"><rect width="56" height="42" fill="#000"/><circle cx="28" cy="21" r="7" fill="none" stroke="#4b5563" stroke-width="2"/></svg>'
  );

function handleThumbnailError(e: React.SyntheticEvent<HTMLImageElement>) {
  e.currentTarget.onerror = null;
  e.currentTarget.src = THUMBNAIL_FALLBACK;
}

function absoluteTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [events, setEvents] = useState<CamEvent[]>([]);
  const [selected, setSelected] = useState<CamEvent | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [cameras, setCameras] = useState<CameraDevice[]>([]);
  const [adjust, setAdjust] = useState<Adjustments | null>(null);
  const adjustTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [hardware, setHw] = useState<HardwareSettings | null>(null);
  const hardwareTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [rotation, setRot] = useState<Rotation | null>(null);
  const [webhookUrl, setWebhookUrlInput] = useState("");
  const [imageToggles, setImageToggles] = useState<ToggleEntry[]>([]);
  const [logOpen, setLogOpen] = useState(true);
  const [cameraOpen, setCameraOpen] = useState(true);

  useEffect(() => {
    const poll = () => {
      getStatus().then(setStatus).catch(() => setStatus(null));
      getEvents().then(setEvents).catch(() => {});
    };
    poll();
    const id = setInterval(poll, 4000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    getCameras()
      .then((r) => setCameras(r.devices))
      .catch(() => {});
  }, []);

  useEffect(() => {
    getAdjustments().then(setAdjust).catch(() => {});
  }, []);

  useEffect(() => {
    getHardware().then(setHw).catch(() => {});
  }, [status?.camera_name]);

  useEffect(() => {
    getRotation().then((r) => setRot(r.rotation)).catch(() => {});
  }, []);

  useEffect(() => {
    getWebhookUrl().then((r) => setWebhookUrlInput(r.url ?? "")).catch(() => {});
  }, []);

  useEffect(() => {
    getToggles().then((t) => setImageToggles(t.image)).catch(() => {});
  }, []);

  const handleCameraChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const index = Number(e.target.value);
    await selectCamera(index);
    getStatus().then(setStatus).catch(() => {});
  };

  const handleDetectorToggle = async (name: string, currentEnabled: boolean) => {
    const updated = await toggleDetector(name, !currentEnabled);
    // Merge just `enabled` rather than replacing the whole entry -- the
    // toggle endpoint's response doesn't include `heavy`/`links`, and a
    // wholesale replace would wipe those out of the already-loaded status.
    setStatus((s) =>
      s ? { ...s, detectors: s.detectors.map((d) => (d.name === name ? { ...d, enabled: updated.enabled } : d)) } : s
    );
  };

  const handleActionToggle = async (name: string, currentEnabled: boolean) => {
    const updated = await toggleAction(name, !currentEnabled);
    setStatus((s) => (s ? { ...s, actions: s.actions.map((a) => (a.name === name ? updated : a)) } : s));
  };

  const handlePipelineLinkToggle = async (detectorName: string, actionName: string, currentlyLinked: boolean) => {
    await togglePipelineLink(detectorName, actionName, !currentlyLinked);
    setStatus((s) =>
      s
        ? {
            ...s,
            detectors: s.detectors.map((d) =>
              d.name === detectorName ? { ...d, links: { ...d.links, [actionName]: !currentlyLinked } } : d
            ),
          }
        : s
    );
  };

  const handleWebhookUrlSave = async () => {
    await setWebhookUrl(webhookUrl.trim());
  };

  const handleImageToggle = async (name: string, currentEnabled: boolean) => {
    const updated = await toggleGeneric("image", name, !currentEnabled);
    setImageToggles((toggles) => toggles.map((t) => (t.name === name ? updated : t)));
  };

  const handleOpenFolder = async () => {
    try {
      await openRecordingsFolder();
    } catch {
      // Most likely a non-Windows host or the folder doesn't exist yet -- no fanfare needed.
    }
  };

  const handlePauseToggle = async () => {
    if (!status) return;
    const updated = await pauseCamera(!status.paused);
    setStatus((s) => (s ? { ...s, paused: updated.paused } : s));
  };

  const handleFlagToggle = async (ev: CamEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = await setEventFlag(ev.id, !ev.flagged);
    setEvents((evs) => evs.map((x) => (x.id === ev.id ? { ...x, flagged: updated.flagged } : x)));
    setSelected((s) => (s && s.id === ev.id ? { ...s, flagged: updated.flagged } : s));
  };

  const handleDelete = async (ev: CamEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    if (ev.flagged && !window.confirm("Delete this flagged event permanently?")) return;
    await deleteEvent(ev.id);
    setEvents((evs) => evs.filter((x) => x.id !== ev.id));
    setSelected((s) => (s && s.id === ev.id ? null : s));
  };

  const openEvent = (ev: CamEvent) => {
    // No video yet (still recording, or it never got one) -- nothing to
    // preview. Opening the modal anyway would just show a broken player.
    if (!ev.video) return;
    setVideoFailed(false);
    setSelected(ev);
  };

  const handleAdjustChange = (key: keyof Adjustments, value: number) => {
    setAdjust((a) => (a ? { ...a, [key]: value } : a));
    if (adjustTimer.current) clearTimeout(adjustTimer.current);
    adjustTimer.current = setTimeout(() => {
      setAdjustments({ [key]: value });
    }, 150);
  };

  const handleAdjustReset = async () => {
    const reset = await setAdjustments({ brightness: 0, contrast: 1, saturation: 1 });
    setAdjust(reset);
  };

  const handleHardwareChange = (key: "exposure" | "brightness", value: number) => {
    setHw((h) => (h ? { ...h, [key]: value } : h));
    if (hardwareTimer.current) clearTimeout(hardwareTimer.current);
    hardwareTimer.current = setTimeout(() => {
      setHardware({ [key]: value });
    }, 150);
  };

  const handleRotationChange = async (value: Rotation) => {
    setRot(value);
    const updated = await setRotation(value);
    setRot(updated.rotation);
  };

  const handleAutoExposureToggle = async () => {
    if (!hardware) return;
    const updated = await setHardware({ auto_exposure: !hardware.auto_exposure });
    setHw(updated);
  };

  return (
    <div className={`workspace ${!logOpen ? "right-collapsed" : ""} ${!cameraOpen ? "bottom-collapsed" : ""}`}>
      <div className="stage">
        {status?.recording && (
          <div className="stage-badge stage-badge-rec">
            <span className="rec-dot" /> REC
          </div>
        )}
        <div className="stage-badge stage-badge-status">
          <span className={`dot ${status?.connected ? "dot-online" : "dot-offline"}`} />
          {status?.paused ? "Paused" : status?.connected ? `Live · ${status.fps} fps` : "Disconnected"}
        </div>
        {status?.shutting_down && <div className="live-overlay live-overlay-shutdown">Webcam Tools is shutting down…</div>}
        {!status?.shutting_down && status?.paused && (
          <div className="live-overlay">Camera paused — released for other apps</div>
        )}
        {!status?.shutting_down && !status?.paused && status?.connected === false && (
          <div className="live-overlay">Waiting for camera…</div>
        )}
        <img
          key={streamKey}
          src="/api/stream"
          alt="Live camera feed"
          onError={() => setTimeout(() => setStreamKey((k) => k + 1), 2000)}
        />
      </div>

      {cameraOpen ? (
        <section className="dock dock-bottom">
          <Tabs.Root className="dock-tabs" defaultValue="camera">
            <div className="dock-header">
              <Tabs.List className="tabs">
                <Tabs.Trigger className="tab" value="camera">
                  Camera
                </Tabs.Trigger>
                <Tabs.Trigger className="tab" value="pipeline">
                  Pipeline
                </Tabs.Trigger>
              </Tabs.List>
              <button className="dock-collapse" onClick={() => setCameraOpen(false)} title="Collapse">
                ⌄
              </button>
            </div>

            <Tabs.Content value="camera" className="dock-body">
              <div className="toolbar">
                <button className="toolbar-btn" onClick={handlePauseToggle}>
                  {status?.paused ? "Resume camera" : "Pause camera"}
                </button>
                {cameras.length > 0 && (
                  <select
                    className="toolbar-select"
                    value={status?.camera_index ?? ""}
                    onChange={handleCameraChange}
                  >
                    {cameras.map((c) => (
                      <option key={c.index} value={c.index}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  className="toolbar-btn"
                  onClick={handleOpenFolder}
                  title="Opens the recordings folder in Explorer on the Webcam Tools host machine"
                >
                  Open recordings folder
                </button>
              </div>

              <div className="settings-panel">
                {hardware && (
                  <div className="settings-group">
                    <div className="settings-group-title">
                      Exposure (hardware{hardware.camera_name ? ` · ${hardware.camera_name}` : ""})
                    </div>
                    <div className="slider-row">
                      <span className="slider-label">Auto exposure</span>
                      <ToggleSwitch checked={hardware.auto_exposure} onChange={handleAutoExposureToggle} />
                      <span className="slider-value" />
                    </div>
                    <SliderRow
                      label="Exposure"
                      min={-13}
                      max={0}
                      disabled={hardware.auto_exposure}
                      value={hardware.exposure}
                      onChange={(v) => handleHardwareChange("exposure", v)}
                    />
                    <SliderRow
                      label="Brightness"
                      min={0}
                      max={255}
                      value={hardware.brightness}
                      onChange={(v) => handleHardwareChange("brightness", v)}
                    />
                  </div>
                )}

                {rotation !== null && (
                  <div className="settings-group">
                    <div className="settings-group-title">Rotation</div>
                    <div className="rotation-buttons">
                      {([0, 90, 180, 270] as Rotation[]).map((deg) => (
                        <button
                          key={deg}
                          className={`rotation-btn${rotation === deg ? " active" : ""}`}
                          onClick={() => handleRotationChange(deg)}
                        >
                          {deg}°
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {adjust && (
                  <div className="settings-group">
                    <div className="settings-group-title">Post-processing</div>
                    <SliderRow
                      label="Brightness"
                      min={-100}
                      max={100}
                      value={adjust.brightness}
                      onChange={(v) => handleAdjustChange("brightness", v)}
                    />
                    <SliderRow
                      label="Contrast"
                      min={50}
                      max={200}
                      step={5}
                      value={Math.round(adjust.contrast * 100)}
                      displayValue={`${Math.round(adjust.contrast * 100)}%`}
                      onChange={(v) => handleAdjustChange("contrast", v / 100)}
                    />
                    <SliderRow
                      label="Saturation"
                      min={0}
                      max={200}
                      step={5}
                      value={Math.round(adjust.saturation * 100)}
                      displayValue={`${Math.round(adjust.saturation * 100)}%`}
                      onChange={(v) => handleAdjustChange("saturation", v / 100)}
                    />
                    {imageToggles.map((t) => (
                      <div className="slider-row" key={t.name}>
                        <span className="slider-label">{t.name.replace(/_/g, " ")}</span>
                        <ToggleSwitch checked={t.enabled} onChange={() => handleImageToggle(t.name, t.enabled)} />
                        <span className="slider-value" />
                      </div>
                    ))}
                    <button className="adjust-reset" onClick={handleAdjustReset}>
                      Reset
                    </button>
                  </div>
                )}
              </div>
            </Tabs.Content>

            <Tabs.Content value="pipeline" className="dock-body">
              <div className="pipeline-actions-legend">
                {(status?.actions ?? []).map((a) => (
                  <div className="pipeline-action-row" key={a.name}>
                    <ToggleSwitch checked={a.enabled} onChange={() => handleActionToggle(a.name, a.enabled)} />
                    <span className="pipeline-action-row-name">{a.name.replace(/_/g, " ")}</span>
                    {a.name === "webhook" && (
                      <input
                        className="pipeline-webhook-input"
                        type="text"
                        placeholder="https://maker.ifttt.com/trigger/.../with/key/..."
                        value={webhookUrl}
                        onChange={(e) => setWebhookUrlInput(e.target.value)}
                        onBlur={handleWebhookUrlSave}
                      />
                    )}
                  </div>
                ))}
              </div>

              <div className="pipeline-stages">
                {(status?.detectors ?? []).map((d) => (
                  <div className="pipeline-stage" key={d.name}>
                    <span className="pipeline-stage-name">
                      {d.name}
                      {d.heavy && <span className="pipeline-stage-heavy-badge">slow</span>}
                    </span>
                    <ToggleSwitch checked={d.enabled} onChange={() => handleDetectorToggle(d.name, d.enabled)} />
                    <span className="pipeline-arrow">→</span>
                    {(status?.actions ?? []).map((a) => {
                      const linked = d.links[a.name] ?? true;
                      return (
                        <button
                          key={a.name}
                          className={`pipeline-action-chip ${linked ? "" : "pipeline-action-chip-off"}`}
                          onClick={() => handlePipelineLinkToggle(d.name, a.name, linked)}
                          title={
                            linked
                              ? `${d.name} → ${a.name}: click to unlink`
                              : `${d.name} → ${a.name}: click to link`
                          }
                        >
                          {a.name.replace(/_/g, " ")}
                        </button>
                      );
                    })}
                  </div>
                ))}
                <div className="pipeline-stage pipeline-stage-ghost">+ Add stage</div>
              </div>
            </Tabs.Content>
          </Tabs.Root>
        </section>
      ) : (
        <button className="dock-bar dock-bar-bottom" onClick={() => setCameraOpen(true)} title="Expand">
          ⌃ Camera settings
        </button>
      )}

      {logOpen ? (
        <aside className="dock dock-right">
          <Tabs.Root className="dock-tabs" defaultValue="log">
            <div className="dock-header">
              <Tabs.List className="tabs">
                <Tabs.Trigger className="tab" value="log">
                  Event log
                </Tabs.Trigger>
              </Tabs.List>
              <button className="dock-collapse" onClick={() => setLogOpen(false)} title="Collapse">
                ›
              </button>
            </div>

            <Tabs.Content value="log" className="dock-body dock-body-log">
              {events.length === 0 && <p className="empty">No events yet.</p>}
              <ul className="event-list">
                {events.map((ev) => (
                  <li
                    key={ev.id}
                    className={`event-item ${!ev.video ? "event-item-pending" : ""}`}
                    onClick={() => openEvent(ev)}
                    title={ev.video ? undefined : "Still recording — not ready to preview yet"}
                  >
                    {Date.now() / 1000 - ev.timestamp < THUMBNAIL_PENDING_SECONDS ? (
                      <div className="thumb-pending">
                        <span className="rec-dot" />
                      </div>
                    ) : (
                      <img src={`/api/events/${ev.id}/image`} alt={ev.type} onError={handleThumbnailError} />
                    )}
                    <div className="event-info">
                      <div className="event-type">
                        {ev.type}
                        {ev.video && <span className="video-badge">▶</span>}
                      </div>
                      <div className="event-time" title={absoluteTime(ev.timestamp)}>
                        {timeAgo(ev.timestamp)}
                      </div>
                    </div>
                    <button
                      className={`flag-btn ${ev.flagged ? "flagged" : ""}`}
                      onClick={(e) => handleFlagToggle(ev, e)}
                      title={ev.flagged ? "Keep (won't be auto-deleted)" : "Flag to keep"}
                    >
                      {ev.flagged ? "★" : "☆"}
                    </button>
                    <button className="delete-btn" onClick={(e) => handleDelete(ev, e)} title="Delete permanently">
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </Tabs.Content>
          </Tabs.Root>
        </aside>
      ) : (
        <button className="dock-bar dock-bar-right" onClick={() => setLogOpen(true)} title="Expand">
          ‹ Event log
        </button>
      )}

      {selected && (
        <div className="modal" onClick={() => setSelected(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-time">{absoluteTime(selected.timestamp)}</div>
            {selected.video && !videoFailed ? (
              <video
                src={`/api/events/${selected.id}/video`}
                controls
                autoPlay
                onError={() => setVideoFailed(true)}
              />
            ) : (
              <img src={`/api/events/${selected.id}/image`} alt={selected.type} />
            )}
            <div className="modal-actions">
              <button
                className={`flag-btn modal-flag-btn ${selected.flagged ? "flagged" : ""}`}
                onClick={(e) => handleFlagToggle(selected, e)}
              >
                {selected.flagged ? "★ Keeping" : "☆ Flag to keep"}
              </button>
              <button className="delete-btn modal-delete-btn" onClick={(e) => handleDelete(selected, e)}>
                ✕ Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
