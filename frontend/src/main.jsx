import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const LAST_JOB_KEY = 'aifv:lastJobId';
const pathKey = (jobId) => `aifv:path:${jobId}`;

const GENRES = [
  ['absurd_comedy', 'Absurd comedy'],
  ['light_comedy', 'Light comedy'],
  ['cinematic_drama', 'Cinematic drama'],
  ['sci_fi', 'Science fiction'],
  ['fantasy', 'Fantasy adventure'],
  ['action', 'Action adventure'],
  ['mystery', 'Mystery / suspense'],
  ['romance', 'Romance'],
  ['documentary', 'Mini documentary'],
  ['advertisement', 'Advertisement / product demo'],
];

const PROVIDERS = [
  ['mock', 'Local demo — no API key required'],
  ['veo_lite', 'Google Veo Lite — text-to-video with audio'],
  ['veo_fast', 'Google Veo Fast — text-to-video with audio'],
  ['veo_standard', 'Google Veo Standard — text-to-video with audio'],
  ['fal', 'fal.ai Seedance 2.0 — optional video reference, may trigger audio/content filters'],
];

function App() {
  const [job, setJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [graph, setGraph] = useState(null);
  const [currentId, setCurrentId] = useState(null);
  const [pathStack, setPathStack] = useState([]);
  const [showChoices, setShowChoices] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [restoreJobId, setRestoreJobId] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);

  const [inputMode, setInputMode] = useState('text');
  const [selectedFile, setSelectedFile] = useState(null);
  const [inputText, setInputText] = useState('');
  const [clipLengthSeconds, setClipLengthSeconds] = useState(15);
  const [genre, setGenre] = useState('absurd_comedy');
  const [videoProvider, setVideoProvider] = useState('mock');

  const pollRef = useRef(null);

  useEffect(() => {
    refreshJobs();
    const lastJobId = window.localStorage.getItem(LAST_JOB_KEY);
    if (lastJobId) {
      setRestoreJobId(lastJobId);
      loadExistingJob(lastJobId, { silent: true });
    }
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    if (job?.job_id && pathStack.length > 0) {
      window.localStorage.setItem(LAST_JOB_KEY, job.job_id);
      window.localStorage.setItem(pathKey(job.job_id), JSON.stringify(pathStack));
    }
  }, [job?.job_id, pathStack]);

  const nodeMap = useMemo(() => {
    const m = new Map();
    graph?.nodes?.forEach((n) => m.set(n.id, n));
    return m;
  }, [graph]);

  const currentNode = currentId ? nodeMap.get(currentId) : null;
  const outgoing = useMemo(() => {
    if (!graph || !currentId) return [];
    return graph.edges
      .filter((e) => e.source === currentId)
      .map((e) => ({ edge: e, node: nodeMap.get(e.target) }))
      .filter((x) => x.node);
  }, [graph, currentId, nodeMap]);

  async function refreshJobs() {
    try {
      const res = await fetch(`${API_BASE}/api/jobs?limit=20`);
      if (!res.ok) return;
      const data = await res.json();
      setJobs(data);
    } catch {
      // Backend may not be running yet. Keep the UI usable.
    }
  }

  function resetPlayerState() {
    setGraph(null);
    setCurrentId(null);
    setPathStack([]);
    setShowChoices(false);
  }

  async function submitJob() {
    setUploadError('');

    if (inputMode === 'video' && !selectedFile) {
      setUploadError('Please choose a source video, or switch to text input mode.');
      return;
    }
    if (inputMode === 'text' && !inputText.trim()) {
      setUploadError('Please enter a text concept, or switch to video input mode.');
      return;
    }

    setIsUploading(true);
    resetPlayerState();

    const body = new FormData();
    body.append('input_mode', inputMode);
    body.append('input_text', inputText.trim());
    body.append('genre', genre);
    body.append('clip_length_seconds', String(clipLengthSeconds));
    body.append('video_provider', videoProvider);
    if (inputMode === 'video' && selectedFile) {
      body.append('video', selectedFile);
    }

    try {
      const res = await fetch(`${API_BASE}/api/jobs`, { method: 'POST', body });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJob(data);
      setRestoreJobId(data.job_id);
      window.localStorage.setItem(LAST_JOB_KEY, data.job_id);
      await refreshJobs();
      startPolling(data.job_id);
    } catch (err) {
      setUploadError(String(err.message || err));
    } finally {
      setIsUploading(false);
    }
  }

  async function retryJob(jobId) {
    const id = (jobId || '').trim();
    if (!id) return;
    if (pollRef.current) window.clearInterval(pollRef.current);
    setUploadError('');
    setIsRestoring(true);
    resetPlayerState();
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${id}/retry`, { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJob(data);
      setRestoreJobId(data.job_id);
      window.localStorage.setItem(LAST_JOB_KEY, data.job_id);
      await refreshJobs();
      if (data.status === 'completed') {
        await loadGraphForJob(data);
      } else {
        startPolling(data.job_id);
      }
    } catch (err) {
      setUploadError(String(err.message || err));
      await loadExistingJob(id, { silent: true });
    } finally {
      setIsRestoring(false);
    }
  }

  async function loadExistingJob(jobId, options = {}) {
    const id = (jobId || '').trim();
    if (!id) return;
    if (pollRef.current) window.clearInterval(pollRef.current);
    setUploadError('');
    setIsRestoring(true);
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${id}`);
      if (!res.ok) throw new Error(`Job not found or backend cannot read it: ${id}`);
      const data = await res.json();
      setJob(data);
      setRestoreJobId(data.job_id);
      window.localStorage.setItem(LAST_JOB_KEY, data.job_id);
      resetPlayerState();

      if (data.status === 'completed') {
        await loadGraphForJob(data);
      } else if (['queued', 'analyzing', 'generating', 'concatenating'].includes(data.status)) {
        startPolling(data.job_id);
      }
      await refreshJobs();
    } catch (err) {
      if (!options.silent) setUploadError(String(err.message || err));
    } finally {
      setIsRestoring(false);
    }
  }

  async function loadGraphForJob(jobStatus) {
    const graphRes = await fetch(`${API_BASE}${jobStatus.graph_url || `/api/jobs/${jobStatus.job_id}/graph`}`);
    if (!graphRes.ok) throw new Error('Graph is not ready yet.');
    const g = await graphRes.json();
    setGraph(g);

    const nodeIds = new Set((g.nodes || []).map((n) => n.id));
    let restoredStack = [];
    try {
      restoredStack = JSON.parse(window.localStorage.getItem(pathKey(jobStatus.job_id)) || '[]');
    } catch {
      restoredStack = [];
    }
    restoredStack = restoredStack.filter((id) => nodeIds.has(id));

    const root = g.root_id || 'clip1';
    const nextStack = restoredStack.length > 0 ? restoredStack : [root];
    setCurrentId(nextStack[nextStack.length - 1] || root);
    setPathStack(nextStack);
    setShowChoices(false);
  }

  function startPolling(jobId) {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
      if (!res.ok) return;
      const data = await res.json();
      setJob(data);
      if (data.status === 'completed') {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
        await loadGraphForJob(data);
        await refreshJobs();
      }
      if (data.status === 'failed') {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
        await refreshJobs();
      }
    }, 1800);
  }

  function chooseNode(targetId) {
    setCurrentId(targetId);
    setPathStack((prev) => [...prev, targetId]);
    setShowChoices(false);
  }

  function jumpToStackIndex(index) {
    const targetId = pathStack[index];
    setCurrentId(targetId);
    setPathStack((prev) => prev.slice(0, index + 1));
    setShowChoices(false);
  }

  function startNewUpload() {
    if (pollRef.current) window.clearInterval(pollRef.current);
    setJob(null);
    resetPlayerState();
    setUploadError('');
  }

  function videoSrc(node) {
    if (!job || !node?.filename) return '';
    return `${API_BASE}/media/${job.job_id}/${node.filename}`;
  }

  const providerHint = videoProvider.startsWith('veo')
    ? 'Veo receives text prompts. If you upload a video, Gemini analyzes it first. Set your Gemini key in the backend configuration to use this provider.'
    : videoProvider === 'fal'
      ? 'Seedance can use the uploaded video as a reference for the first root segment, but native audio may be filtered by the provider.'
      : 'Local demo creates placeholder videos with sound. It uses no API keys or external AI services.';

  const clipHint = videoProvider.startsWith('veo')
    ? (clipLengthSeconds === 15 ? 'Veo uses its longest 8s generation twice, so each clip is about 16s.' : 'Veo uses its longest 8s generation eight times, so each clip is about 64s.')
    : videoProvider === 'mock'
      ? (clipLengthSeconds === 15 ? 'Two local 8-second segments form each 16-second clip.' : 'Eight local 8-second segments form each 64-second clip.')
      : 'The backend rounds the requested length up to a whole number of configured segments.';

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">MVP</p>
          <h1>AI Interactive Video</h1>
          <p className="subtitle">
            Upload a video or enter a text concept. The backend creates a directed graph of AI-generated clips.
            After each clip ends, choices appear directly inside the video area.
          </p>
        </div>
        {(job || graph) && (
          <button className="hero-button" onClick={startNewUpload}>
            New job
          </button>
        )}
      </header>

      {!graph && (
        <section className="card upload-card">
          <h2>1. Create an interactive video graph</h2>
          <p>
            Start with the local demo to try branching videos. Choose a provider and configure its API key to generate AI clips.
          </p>

          <div className="form-grid">
            <label className="field full">
              <span>Input type</span>
              <div className="segmented">
                <button className={inputMode === 'video' ? 'selected' : ''} onClick={() => setInputMode('video')} type="button">Upload video</button>
                <button className={inputMode === 'text' ? 'selected' : ''} onClick={() => setInputMode('text')} type="button">Pure text</button>
              </div>
            </label>

            {inputMode === 'video' ? (
              <label className="field full">
                <span>Source video</span>
                <input
                  type="file"
                  accept="video/*"
                  disabled={isUploading || isRestoring}
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
              </label>
            ) : (
              <label className="field full">
                <span>Text concept</span>
                <textarea
                  placeholder="Example: A cinematic sci-fi story about a tiny robot escaping a university lab, with choices after each scene."
                  value={inputText}
                  disabled={isUploading || isRestoring}
                  onChange={(e) => setInputText(e.target.value)}
                />
              </label>
            )}

            <label className="field">
              <span>Video provider</span>
              <select value={videoProvider} onChange={(e) => setVideoProvider(e.target.value)} disabled={isUploading || isRestoring}>
                {PROVIDERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <small>{providerHint}</small>
            </label>

            <label className="field">
              <span>Genre / topic</span>
              <select value={genre} onChange={(e) => setGenre(e.target.value)} disabled={isUploading || isRestoring}>
                {GENRES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>

            <label className="field full">
              <span>Clip length per graph node</span>
              <div className="segmented">
                <button className={clipLengthSeconds === 15 ? 'selected' : ''} onClick={() => setClipLengthSeconds(15)} type="button">15 seconds</button>
                <button className={clipLengthSeconds === 60 ? 'selected' : ''} onClick={() => setClipLengthSeconds(60)} type="button">1 minute</button>
              </div>
              <small>{clipHint}</small>
            </label>
          </div>

          <button className="primary-action" disabled={isUploading || isRestoring} onClick={submitJob}>
            {isUploading ? 'Uploading...' : 'Start generation'}
          </button>

          <div className="restore-box">
            <h3>Restore generated result</h3>
            <p className="muted">
              Generated videos are stored on the backend by job_id. Reopen the page later and load a previous job
              without regenerating videos.
            </p>
            <div className="restore-row">
              <input
                type="text"
                placeholder="Paste job_id, for example: 3f1a9c8d2e4b6a00"
                value={restoreJobId}
                onChange={(e) => setRestoreJobId(e.target.value)}
              />
              <button disabled={isRestoring} onClick={() => loadExistingJob(restoreJobId)}>
                {isRestoring ? 'Loading...' : 'Load'}
              </button>
            </div>

            {jobs.length > 0 && (
              <div className="history-list">
                <div className="history-title-row">
                  <h4>Recent jobs</h4>
                  <button className="text-button" onClick={refreshJobs}>Refresh</button>
                </div>
                {jobs.map((item) => (
                  <button
                    key={item.job_id}
                    className="history-item"
                    onClick={() => item.status === 'failed' ? retryJob(item.job_id) : loadExistingJob(item.job_id)}
                  >
                    <span>
                      <b>{item.input_filename || item.input_text || item.job_id}</b>
                      <small>{item.job_id} · {item.video_provider} · {item.genre} · {item.status} · {new Date(item.updated_at).toLocaleString()}</small>
                    </span>
                    <em>{item.status === 'completed' ? 'Open' : item.status === 'failed' ? 'Retry' : 'Watch'}</em>
                  </button>
                ))}
              </div>
            )}
          </div>
          {uploadError && <p className="error">{uploadError}</p>}
        </section>
      )}

      {job && !graph && <JobProgress job={job} onRetry={() => retryJob(job.job_id)} />}

      {graph && currentNode && (
        <section className="player-layout">
          <div className="video-panel">
            <div className="video-box">
              <video
                key={currentNode.id}
                src={videoSrc(currentNode)}
                controls
                autoPlay
                playsInline
                onPlay={() => setShowChoices(false)}
                onEnded={() => setShowChoices(true)}
              />

              {showChoices && (
                <div className="choice-overlay">
                  <div className="choice-card">
                    <p className="overlay-title">Choose the next scene</p>
                    <h2>{currentNode.title || currentNode.option}</h2>
                    {outgoing.length === 0 ? (
                      <button onClick={() => chooseNode(graph.root_id || 'clip1')}>Restart from beginning</button>
                    ) : (
                      outgoing.map(({ edge, node }) => (
                        <button key={`${edge.source}-${edge.target}-${edge.label}`} onClick={() => chooseNode(node.id)}>
                          {edge.label || node.option}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <aside className="side-card">
            <h2>Current node</h2>
            <p className="node-id">{currentNode.id}</p>
            <h3>{currentNode.title || currentNode.option}</h3>
            <p>{currentNode.description}</p>

            <h2>Choice path stack</h2>
            <p className="muted">Click a previous node to pop everything after it.</p>
            <div className="stack-list">
              {pathStack.map((id, idx) => {
                const n = nodeMap.get(id);
                return (
                  <button
                    className={idx === pathStack.length - 1 ? 'active' : ''}
                    key={`${id}-${idx}`}
                    onClick={() => jumpToStackIndex(idx)}
                  >
                    {idx + 1}. {n?.option || id}
                  </button>
                );
              })}
            </div>

            <a className="small-link" href={`${API_BASE}/api/jobs/${job.job_id}/graph`} target="_blank" rel="noreferrer">
              Open graph.json
            </a>
          </aside>
        </section>
      )}
    </main>
  );
}

function JobProgress({ job, onRetry }) {
  return (
    <section className="card progress-card">
      <div className="progress-topline">
        <h2>2. Backend processing</h2>
        <span>{Math.round((job.progress || 0) * 100)}%</span>
      </div>
      <div className="progress-bar">
        <div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
      </div>
      <p className={job.status === 'failed' ? 'error' : ''}>
        <b>Status:</b> {job.status} — {job.message}
      </p>
      <p className="muted"><b>job_id:</b> {job.job_id}</p>
      <p className="muted"><b>provider:</b> {job.video_provider} · <b>genre:</b> {job.genre} · <b>clip length:</b> {job.clip_length_seconds}s</p>
      {job.status === 'failed' && (
        <button className="primary-action compact" onClick={onRetry}>
          Retry / resume this failed job
        </button>
      )}
      <div className="log-box">
        {(job.logs || []).slice(-16).map((line, idx) => (
          <p key={idx}>{line}</p>
        ))}
      </div>
    </section>
  );
}

createRoot(document.getElementById('root')).render(<App />);
