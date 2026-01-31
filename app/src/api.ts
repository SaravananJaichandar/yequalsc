/**
 * API client for y=c backend
 */

const API_BASE = 'http://localhost:8000';

export interface UploadResponse {
  status: string;
  message: string;
  file_path: string;
  source_type: string;
}

export interface IngestionStatus {
  active: boolean;
  current_file: string;
  progress: number;
  total_files: number;
  completed_files: number;
  chunks_added: number;
  error: string | null;
}

export interface SearchResult {
  text: string;
  source: string;
  source_type: string;
  score: number;
}

export interface QueryResponse {
  answer: string;
  sources: SearchResult[];
  status: string;
}

export interface StatsResponse {
  status: string;
  stats: {
    total_chunks: number;
    sources: string[];
    by_type: Record<string, number>;
    source_count: number;
  };
  error?: string;
}

/**
 * Check if the backend is running
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`);
    const data = await response.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
}

/**
 * Get database statistics
 */
export async function getStats(): Promise<StatsResponse> {
  const response = await fetch(`${API_BASE}/stats`);
  return response.json();
}

/**
 * Upload a file for ingestion
 */
export async function uploadFile(
  file: File,
  sourceType: 'claude' | 'chatgpt'
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/upload/${sourceType}`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

/**
 * Start ingestion for a source
 */
export async function startIngestion(
  sourceType: 'claude' | 'chatgpt' | 'notes',
  filePath?: string,
  force: boolean = false
): Promise<{ status: string; source_type: string; file_path?: string }> {
  const response = await fetch(`${API_BASE}/ingest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source_type: sourceType,
      file_path: filePath,
      force,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Ingestion failed to start');
  }

  return response.json();
}

/**
 * Get current ingestion status
 */
export async function getIngestionStatus(): Promise<IngestionStatus> {
  const response = await fetch(`${API_BASE}/ingest/status`);
  return response.json();
}

/**
 * Reset ingestion status (use if stuck)
 */
export async function resetIngestion(): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/ingest/reset`, {
    method: 'POST',
  });
  return response.json();
}

/**
 * Subscribe to ingestion progress via SSE
 */
export function subscribeToIngestionProgress(
  onProgress: (status: IngestionStatus) => void,
  onComplete: (status: IngestionStatus) => void,
  onError: (error: Error) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/ingest/progress`);

  eventSource.onmessage = (event) => {
    try {
      const status: IngestionStatus = JSON.parse(event.data);
      if (status.active) {
        onProgress(status);
      } else {
        onComplete(status);
        eventSource.close();
      }
    } catch (e) {
      onError(e as Error);
    }
  };

  eventSource.onerror = () => {
    onError(new Error('Connection to server lost'));
    eventSource.close();
  };

  // Return cleanup function
  return () => eventSource.close();
}

/**
 * Search memories
 */
export async function searchMemories(
  query: string,
  topK: number = 5
): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, top_k: topK }),
  });

  return response.json();
}

/**
 * Ask a question (with LLM processing)
 */
export async function askQuestion(
  query: string,
  topK: number = 5
): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query, top_k: topK }),
  });

  return response.json();
}

/**
 * Goose status response
 */
export interface GooseStatus {
  installed: boolean;
  configured: boolean;
  recipe_exists?: boolean;
  recipe_path?: string;
  message: string;
}

export interface ModelStatus {
  ready: boolean;
  downloading: boolean;
  error: string | null;
}

export async function getModelStatus(): Promise<ModelStatus> {
  try {
    const response = await fetch(`${API_BASE}/model/status`);
    return response.json();
  } catch {
    return { ready: false, downloading: false, error: null };
  }
}

export async function purgeMemories(): Promise<{ status: string; deleted: number }> {
  const response = await fetch(`${API_BASE}/purge`, { method: 'POST' });
  return response.json();
}

/**
 * Get Goose CLI status
 */
export async function getGooseStatus(): Promise<GooseStatus> {
  try {
    const response = await fetch(`${API_BASE}/goose/status`);
    return response.json();
  } catch {
    return {
      installed: false,
      configured: false,
      message: 'Backend not reachable'
    };
  }
}
